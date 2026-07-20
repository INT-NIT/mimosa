"""Compare two exported resolutions and say exactly where they disagree.

    python check_alignment.py fichier_res-6x.nii.gz fichier_res-8x.nii.gz

Reads the real NIfTI headers and their JSON sidecars, converts both grids back
to native CZI pixel indices, and checks whether the coarse voxels tile the fine
ones. Prints the numbers it used, so nothing has to be taken on trust.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import nibabel as nb
import numpy as np


def load(path: Path):
    img = nb.load(str(path))
    sform = np.asarray(img.get_sform(), dtype=float)

    sidecar = Path(str(path).replace(".nii.gz", ".json"))
    meta = {}
    if sidecar.exists():
        meta = json.loads(sidecar.read_text())

    return img, sform, meta


def describe(name, img, sform, meta):
    print(f"\n--- {name} ---")
    print("  file            :", Path(name).name)
    print("  shape           :", img.shape)
    print("  spacing (mm)    :", [round(float(sform[i, i]), 6) for i in range(3)])
    print("  origin  (mm)    :", [round(float(sform[i, 3]), 6) for i in range(3)])
    for key in (
        "ReductionMethod",
        "SFormOriginConvention",
        "DownsamplingFactor",
        "PixelSize",
        "NativePixelSize",
        "NativeWidthPixels",
        "NativeHeightPixels",
        "ExportedShape",
    ):
        if key in meta:
            print(f"  {key:16s}:", meta[key])
    if "SFormOriginConvention" not in meta:
        print("  !! SFormOriginConvention absent -> sidecar written by the OLD code")


# NIfTI stores the sform as float32. Reconstructing a native pixel index from
# it therefore carries ~1e-3 native pixel of rounding noise, which has nothing
# to do with the grids being aligned. Anything below a hundredth of a native
# pixel is header precision, not a real offset.
TOL_NATIVE_PX = 0.01


def native_axis(sform, meta, axis):
    """Return (center0, step) of this grid, expressed in native pixel index."""
    native_px = float(meta["NativePixelSize"][axis]) * 1e-3  # um -> mm
    n_native = float(
        meta["NativeWidthPixels"] if axis == 0 else meta["NativeHeightPixels"]
    )
    origin = float(sform[axis, 3])
    step_mm = float(sform[axis, axis])

    center0 = origin / native_px + (n_native - 1.0) / 2.0
    step = step_mm / native_px
    return center0, step


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    fine_path, coarse_path = sys.argv[1], sys.argv[2]
    fine_img, fine_sform, fine_meta = load(Path(fine_path))
    coarse_img, coarse_sform, coarse_meta = load(Path(coarse_path))

    describe(fine_path, fine_img, fine_sform, fine_meta)
    describe(coarse_path, coarse_img, coarse_sform, coarse_meta)

    if not fine_meta or not coarse_meta:
        print("\nMissing JSON sidecar, cannot continue.")
        sys.exit(1)

    print("\n" + "=" * 68)
    print("GRIDS EXPRESSED IN NATIVE CZI PIXELS")
    print("=" * 68)

    ok_all = True
    for axis, label in ((0, "X"), (1, "Y")):
        c0_f, step_f = native_axis(fine_sform, fine_meta, axis)
        c0_c, step_c = native_axis(coarse_sform, coarse_meta, axis)
        ratio = step_c / step_f

        print(f"\n[{label}]")
        print(f"  fine   : voxel k center = {c0_f:9.2f} + k * {step_f:.1f}")
        print(f"  coarse : voxel m center = {c0_c:9.2f} + m * {step_c:.1f}")
        print(f"  ratio  : {ratio:.4f}  (should be a whole number)")

        # Left edge of voxel 0 for each grid.
        edge_f = c0_f - step_f / 2.0
        edge_c = c0_c - step_c / 2.0
        print(f"  left edge of voxel 0 : fine {edge_f:+.2f}   coarse {edge_c:+.2f}")

        if abs(edge_f - edge_c) < TOL_NATIVE_PX:
            print("  -> edges start at the same place: grids tile correctly")
        else:
            ok_all = False
            gap = edge_c - edge_f
            print(f"  -> MISALIGNED by {gap:+.2f} native pixels")
            print(f"     = {gap / step_f:+.3f} fine voxels")
            print(f"     = {gap / step_c:+.3f} coarse voxels")

        # Which fine voxels fall inside coarse voxel m?
        for m in (0, 10, 78):
            if m >= coarse_img.shape[axis]:
                continue
            lo = c0_c + m * step_c - step_c / 2.0
            hi = c0_c + m * step_c + step_c / 2.0
            k_lo = (lo - c0_f + step_f / 2.0) / step_f
            k_hi = (hi - c0_f + step_f / 2.0) / step_f
            whole = (
                abs(k_lo - round(k_lo)) < TOL_NATIVE_PX
                and abs(k_hi - round(k_hi)) < TOL_NATIVE_PX
            )
            flag = "OK" if whole else "NOT a whole number of fine voxels"
            print(f"     coarse voxel {m:3d} spans fine voxels "
                  f"[{k_lo:.3f}, {k_hi:.3f}]  {flag}")

    print("\n" + "=" * 68)
    if ok_all:
        print("VERDICT: the two grids tile exactly. Any offset seen in a viewer")
        print("         is a display artifact, not a data problem.")
    else:
        print("VERDICT: the grids really are shifted. The numbers above say by")
        print("         how much and on which axis.")
    print("=" * 68)


if __name__ == "__main__":
    main()
