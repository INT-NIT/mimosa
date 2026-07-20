"""Diagnostic: is pylibCZIrw's `zoom` read exact, or does it invent values?

Run this on the HPC, where the CZI files live:

    python check_zoom_exactness.py /envau/.../fichier.czi 16

It answers three questions:

  1. Does `zoom` return real native pixels (nearest neighbour), or blended
     values that exist nowhere in the file?
  2. If it returns real pixels, on which grid offset?
  3. How much faster is it, really?

Interpretation
--------------
  VERDICT EXACT      -> `zoom` is safe. Use the fast path, no quantification
                        is harmed. Only the sform origin needs care.
  VERDICT SHIFTED    -> `zoom` keeps real pixels but on a shifted grid. Safe
                        for intensities, needs an origin correction.
  VERDICT BLENDED    -> `zoom` invents values (pyramid averaging or bilinear).
                        Do NOT use it for quantitative work.
"""

from __future__ import annotations

import sys
import time

import numpy as np
from pylibCZIrw import czi as pyczi


def _read(doc, roi, scene, channel, zoom=None):
    kwargs = {"roi": roi, "plane": {"C": channel}, "scene": scene}
    if zoom is not None:
        kwargs["zoom"] = zoom
    arr = np.asarray(doc.read(**kwargs)).squeeze()
    if arr.ndim == 3:
        arr = arr[..., 0]
    return arr


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    czi_path = sys.argv[1]
    factor = int(sys.argv[2]) if len(sys.argv) > 2 else 16
    channel = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    with pyczi.open_czi(czi_path) as doc:
        scenes = doc.scenes_bounding_rectangle
        scene_idx = sorted(scenes)[0] if isinstance(scenes, dict) else 0
        rect = scenes[scene_idx]
        x0, y0, w, h = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))

        print("=" * 70)
        print("FILE   :", czi_path)
        print("SCENE  :", scene_idx, "  native size:", w, "x", h)
        print("FACTOR :", factor, " (i.e. res label", f"{factor.bit_length()-1}x)")
        print("=" * 70)

        # ---- 1. Pyramid present? -------------------------------------
        try:
            info = doc.total_bounding_box
            print("\n[1] total_bounding_box:", info)
        except Exception as exc:
            print("\n[1] bounding box unavailable:", exc)

        try:
            meta = doc.raw_metadata
            has_pyramid = "PyramidType" in meta or "SubBlockPyramid" in meta
            print("    pyramid mentioned in metadata:", has_pyramid)
            if has_pyramid:
                print("    -> `zoom` may read ZEN-generated pyramid levels,")
                print("       which are usually AVERAGED (invented values).")
        except Exception as exc:
            print("    raw_metadata unavailable:", exc)

        # ---- 2. Small aligned test ROI -------------------------------
        side = factor * 32
        tw = min(side, (w // factor) * factor)
        th = min(side, (h // factor) * factor)
        roi = (x0, y0, tw, th)
        print(f"\n[2] test ROI: {tw} x {th} native pixels")

        t = time.perf_counter()
        native = _read(doc, roi, scene_idx, channel)
        t_native = time.perf_counter() - t

        t = time.perf_counter()
        zoomed = _read(doc, roi, scene_idx, channel, zoom=1.0 / factor)
        t_zoom = time.perf_counter() - t

        print("    native read:", native.shape, native.dtype, f"{t_native:.3f}s")
        print("    zoom   read:", zoomed.shape, zoomed.dtype, f"{t_zoom:.3f}s")
        if t_zoom > 0:
            print(f"    speedup on this ROI: x{t_native / t_zoom:.1f}")

        decimated = native[::factor, ::factor]
        print("    exact decimation:", decimated.shape)

        # ---- 3. Exactness --------------------------------------------
        print("\n[3] VERDICT")

        ny = min(zoomed.shape[0], decimated.shape[0])
        nx = min(zoomed.shape[1], decimated.shape[1])
        z = zoomed[:ny, :nx].astype(np.int64)

        if np.array_equal(z, decimated[:ny, :nx].astype(np.int64)):
            print("    >>> EXACT: zoom == native[::f, ::f], bit for bit.")
            print("    >>> The fast path is safe. Use it.")
            return

        # Which offset, if any, matches?
        best = None
        for dy in range(factor):
            for dx in range(factor):
                cand = native[dy::factor, dx::factor]
                if cand.shape[0] < ny or cand.shape[1] < nx:
                    continue
                if np.array_equal(z, cand[:ny, :nx].astype(np.int64)):
                    best = (dy, dx)
                    break
            if best:
                break

        if best:
            print(f"    >>> SHIFTED: zoom == native[{best[0]}::f, {best[1]}::f]")
            print("    >>> Real native pixels, only the grid offset differs.")
            print("    >>> Intensities are INTACT. Safe for quantification.")
            print(f"    >>> Correct the sform origin by {best} native pixels.")
            return

        # Are the values at least present in their native block?
        invented = 0
        checked = 0
        for k in range(min(ny, 64)):
            for j in range(min(nx, 64)):
                block = native[k * factor:(k + 1) * factor,
                               j * factor:(j + 1) * factor]
                checked += 1
                if zoomed[k, j] not in block:
                    invented += 1

        pct = 100.0 * invented / max(1, checked)
        print(f"    >>> checked {checked} pixels, {invented} ({pct:.1f}%) do not")
        print("        exist anywhere in their native block.")
        if invented == 0:
            print("    >>> NEAREST-NEIGHBOUR on an irregular grid.")
            print("    >>> Values intact, but grid not reproducible. Risky.")
        else:
            print("    >>> BLENDED: zoom INVENTS values (averaging/bilinear).")
            print("    >>> Do NOT use zoom for quantitative fluorescence.")


if __name__ == "__main__":
    main()
