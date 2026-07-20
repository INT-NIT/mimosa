"""Decisive test: full-scene `zoom` vs full-scene native decimation.

    python check_zoom_decisive.py /envau/.../fichier.czi [channel]

No 1x1 reads, no mosaic tile-selection ambiguity: one single big native read
of the whole scene (~3 GB for a 55424x26332 uint16 scene), decimated in NumPy,
compared against the `zoom` output for the exact same ROI.

Whatever this prints is the truth about your data.
"""

from __future__ import annotations

import sys
import time

import numpy as np
from pylibCZIrw import czi as pyczi

FACTORS = (16, 64, 256)


def _read(doc, roi, scene, channel, zoom=None):
    kwargs = {"roi": roi, "plane": {"C": channel}, "scene": scene}
    if zoom is not None:
        kwargs["zoom"] = zoom
    arr = np.asarray(doc.read(**kwargs)).squeeze()
    if arr.ndim == 3:
        arr = arr[..., 0]
    return arr


def compare(zoomed, decim, factor, native):
    ny = min(zoomed.shape[0], decim.shape[0])
    nx = min(zoomed.shape[1], decim.shape[1])
    z = zoomed[:ny, :nx].astype(np.int64)
    d = decim[:ny, :nx].astype(np.int64)

    if np.array_equal(z, d):
        print("       -> EXACT: zoom == native[::f, ::f]")
        return "EXACT"

    diff = z - d
    nz = np.count_nonzero(diff)
    pct = 100.0 * nz / diff.size
    print(f"       differing pixels : {nz}/{diff.size} ({pct:.1f}%)")
    print(f"       max |diff|       : {int(np.abs(diff).max())}")
    print(f"       mean |diff|      : {np.abs(diff).mean():.1f}")

    # Is zoom simply a shifted decimation?
    for dy in (0, 1, factor // 2, factor - 1):
        for dx in (0, 1, factor // 2, factor - 1):
            if dy == 0 and dx == 0:
                continue
            cand = native[dy::factor, dx::factor]
            if cand.shape[0] < ny or cand.shape[1] < nx:
                continue
            if np.array_equal(z, cand[:ny, :nx].astype(np.int64)):
                print(f"       -> SHIFTED: zoom == native[{dy}::f, {dx}::f]")
                print("          Real native values, only the grid offset differs.")
                return "SHIFTED"

    # Is zoom close to a block mean? That is the signature of a ZEN pyramid.
    usable_y = (native.shape[0] // factor) * factor
    usable_x = (native.shape[1] // factor) * factor
    blocks = native[:usable_y, :usable_x].reshape(
        usable_y // factor, factor, usable_x // factor, factor
    )
    means = blocks.mean(axis=(1, 3))
    my = min(ny, means.shape[0])
    mx = min(nx, means.shape[1])
    err_mean = np.abs(z[:my, :mx] - means[:my, :mx]).mean()
    err_decim = np.abs(d[:my, :mx] - means[:my, :mx]).mean()
    print(f"       |zoom  - blockmean| : {err_mean:.1f}")
    print(f"       |decim - blockmean| : {err_decim:.1f}")

    if err_mean < err_decim * 0.5:
        print("       -> AVERAGED: zoom matches a block mean far better than")
        print("          a decimation. This is a ZEN pyramid: invented values.")
        return "AVERAGED"

    print("       -> UNKNOWN resampling. Do not trust zoom for quantification.")
    return "UNKNOWN"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    czi_path = sys.argv[1]
    channel = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    with pyczi.open_czi(czi_path) as doc:
        scenes = doc.scenes_bounding_rectangle
        scene = sorted(scenes)[0] if isinstance(scenes, dict) else 0
        rect = scenes[scene]
        x0, y0, w, h = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
        roi = (x0, y0, w, h)

        gb = w * h * 2 / 1e9
        print("=" * 70)
        print("FILE  :", czi_path)
        print("SCENE :", scene, " size=", (w, h), f" native read ~{gb:.1f} GB")
        print("=" * 70)

        print("\nReading the whole scene natively... (this is the slow part)")
        t = time.perf_counter()
        native = _read(doc, roi, scene, channel)
        t_native = time.perf_counter() - t
        print(f"  done in {t_native:.1f}s, shape={native.shape}, {native.dtype}")

        results = {}
        for factor in FACTORS:
            label = f"res-{factor.bit_length() - 1}x"
            print(f"\n[{label}]  factor = {factor}")

            t = time.perf_counter()
            zoomed = _read(doc, roi, scene, channel, zoom=1.0 / factor)
            t_zoom = time.perf_counter() - t

            decim = native[::factor, ::factor]
            print(f"       zoom  {zoomed.shape} in {t_zoom:.2f}s")
            print(f"       decim {decim.shape} (from the native read)")
            if zoomed.shape != decim.shape:
                lost_y = decim.shape[0] - zoomed.shape[0]
                lost_x = decim.shape[1] - zoomed.shape[1]
                print(f"       zoom DROPS {lost_y} row(s), {lost_x} column(s)")

            results[label] = compare(zoomed, decim, factor, native)

        print("\n" + "=" * 70)
        print("SUMMARY")
        for label, verdict in results.items():
            print(f"  {label:8s} -> {verdict}")
        print(f"\n  native full-scene read: {t_native:.1f}s per scene per channel")
        print("=" * 70)


if __name__ == "__main__":
    main()
