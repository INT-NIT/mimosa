"""Diagnostic: is pylibCZIrw's `zoom` read exact on REAL scene ROIs?

    python check_zoom_exactness.py /envau/.../fichier.czi

Tests every production factor (16, 64, 256 = res-4x, 6x, 8x) in two regimes:

  A. small ROI aligned on the scene origin  -> the easy case
  B. the FULL scene ROI, whose size is NOT a multiple of the factor
     -> the real case, where libCZI rounding can shift the grid

Regime B is verified by spot-checking individual native pixels, so it never
loads the whole scene in RAM.

Finally it times a realistic strip to measure the true speedup of `zoom`.
"""

from __future__ import annotations

import random
import sys
import time

import numpy as np
from pylibCZIrw import czi as pyczi

FACTORS = (16, 64, 256)
SPOT_CHECKS = 40


def _read(doc, roi, scene, channel, zoom=None):
    kwargs = {"roi": roi, "plane": {"C": channel}, "scene": scene}
    if zoom is not None:
        kwargs["zoom"] = zoom
    arr = np.asarray(doc.read(**kwargs)).squeeze()
    if arr.ndim == 3:
        arr = arr[..., 0]
    return arr


def test_aligned(doc, x0, y0, w, h, scene, channel, factor):
    """Regime A: small ROI, size exactly a multiple of factor."""
    side = factor * 32
    tw = min(side, (w // factor) * factor)
    th = min(side, (h // factor) * factor)
    roi = (x0, y0, tw, th)

    native = _read(doc, roi, scene, channel)
    zoomed = _read(doc, roi, scene, channel, zoom=1.0 / factor)
    decim = native[::factor, ::factor]

    ny = min(zoomed.shape[0], decim.shape[0])
    nx = min(zoomed.shape[1], decim.shape[1])
    ok = np.array_equal(zoomed[:ny, :nx], decim[:ny, :nx])
    shape_ok = zoomed.shape == decim.shape

    print(f"    A) aligned {tw}x{th}: zoom{zoomed.shape} vs decim{decim.shape}")
    print(f"       shapes match : {shape_ok}")
    print(f"       values match : {ok}")
    return ok and shape_ok


def test_full_scene(doc, x0, y0, w, h, scene, channel, factor, rng):
    """Regime B: the real full-scene ROI, size not a multiple of factor."""
    roi = (x0, y0, w, h)

    t = time.perf_counter()
    zoomed = _read(doc, roi, scene, channel, zoom=1.0 / factor)
    dt = time.perf_counter() - t

    expected_ceil = ((h + factor - 1) // factor, (w + factor - 1) // factor)
    expected_floor = (h // factor, w // factor)

    print(f"    B) full scene {w}x{h}  (w%f={w % factor}, h%f={h % factor})")
    print(f"       zoom shape   : {zoomed.shape}   read in {dt:.1f}s")
    print(f"       ceil(n/f)    : {expected_ceil}")
    print(f"       floor(n/f)   : {expected_floor}")

    # Spot-check: output pixel (k, j) must equal native pixel (k*f, j*f).
    ny, nx = zoomed.shape
    bad = []
    for _ in range(SPOT_CHECKS):
        k = rng.randrange(ny)
        j = rng.randrange(nx)
        py = y0 + k * factor
        px = x0 + j * factor
        if py >= y0 + h or px >= x0 + w:
            continue
        native_px = _read(doc, (px, py, 1, 1), scene, channel)
        native_val = int(np.asarray(native_px).reshape(-1)[0])
        if int(zoomed[k, j]) != native_val:
            bad.append((k, j, int(zoomed[k, j]), native_val))

    if not bad:
        print(f"       spot-check   : {SPOT_CHECKS}/{SPOT_CHECKS} OK "
              f"-> zoom[k,j] == native[k*f, j*f]")
        return True

    print(f"       spot-check   : {len(bad)} MISMATCH out of {SPOT_CHECKS}")
    for k, j, got, want in bad[:5]:
        print(f"         [{k},{j}] zoom={got} native={want}")
    return False


def bench(doc, x0, y0, w, h, scene, channel):
    """Realistic timing on a wide strip, native vs zoom."""
    strip_h = min(4096, h)
    roi = (x0, y0, w, strip_h)
    print(f"\n[TIMING] strip {w} x {strip_h}")

    t = time.perf_counter()
    _read(doc, roi, scene, channel)
    t_native = time.perf_counter() - t
    print(f"    native      : {t_native:7.2f}s")

    for factor in FACTORS:
        t = time.perf_counter()
        _read(doc, roi, scene, channel, zoom=1.0 / factor)
        t_zoom = time.perf_counter() - t
        speed = t_native / t_zoom if t_zoom > 0 else float("inf")
        print(f"    zoom 1/{factor:<4d}: {t_zoom:7.2f}s   (x{speed:.1f} vs native)")

    print("\n    If all zoom timings are close to the native one, there is no")
    print("    pyramid to exploit: the bottleneck is CZI decompression and the")
    print("    only real speedup left is parallelism across scenes.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    czi_path = sys.argv[1]
    channel = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    rng = random.Random(0)

    with pyczi.open_czi(czi_path) as doc:
        scenes = doc.scenes_bounding_rectangle
        scene = sorted(scenes)[0] if isinstance(scenes, dict) else 0
        rect = scenes[scene]
        x0, y0, w, h = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))

        print("=" * 70)
        print("FILE  :", czi_path)
        print("SCENE :", scene, " origin=", (x0, y0), " size=", (w, h))
        print("=" * 70)

        verdict = {}
        for factor in FACTORS:
            label = f"res-{factor.bit_length() - 1}x"
            print(f"\n[{label}]  factor = {factor}")
            a = test_aligned(doc, x0, y0, w, h, scene, channel, factor)
            b = test_full_scene(doc, x0, y0, w, h, scene, channel, factor, rng)
            verdict[label] = (a, b)

        bench(doc, x0, y0, w, h, scene, channel)

        print("\n" + "=" * 70)
        print("SUMMARY")
        all_ok = True
        for label, (a, b) in verdict.items():
            state = "EXACT" if (a and b) else "NOT EXACT"
            all_ok &= a and b
            print(f"  {label:8s} aligned={a}  full-scene={b}   -> {state}")
        print("=" * 70)
        if all_ok:
            print("=> zoom is safe at every production factor. Restore the fast path.")
        else:
            print("=> zoom drifts on the real ROI. Keep the native decimation.")


if __name__ == "__main__":
    main()