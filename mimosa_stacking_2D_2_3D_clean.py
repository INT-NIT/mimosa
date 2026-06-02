import argparse
import json
from pathlib import Path

import nibabel as nb
import numpy as np

from BIDS import bids_manager as bm
from BIDS import bids_metadata as bmeta


class VolumeBuilder3D:
    """
    Build one 3D NIfTI volume per subject and channel from 2D preprocessed slices.

    Important logic kept:
    - slices are placed in Z using the global SliceIndex -> slice_position mapping
    - X/Y resolution comes from PixelSize
    - Z resolution comes from original_thickness
    - optional reorientation is applied after stacking
    """

    def __init__(
        self,
        bids_root: str,
        original_thickness: float,
        reorient: str = "none",
        res_label: str | None = None,
        debug: bool = True,
    ):
        self.bids_root = Path(bids_root).resolve()
        self.original_thickness = float(original_thickness)
        self.reorient = reorient
        self.res_label = res_label
        self.debug = debug

        suffix = f"_res-{res_label}" if res_label else ""
        self.preproc_root = self.bids_root / "derivatives" / f"2D-preproc{suffix}"
        self.stacking_root = self.bids_root / "derivatives" / f"3D-stacking{suffix}"

    # -------------------------------------------------------------------------
    # Small helpers
    # -------------------------------------------------------------------------

    def log(self, *args) -> None:
        if self.debug:
            print(*args)

    def output_path(self, subject_dir: Path, channel: str, res_label: str | None) -> Path:
        out_dir = self.stacking_root / subject_dir.name / "micr"
        out_dir.mkdir(parents=True, exist_ok=True)

        if res_label:
            filename = f"{subject_dir.name}_{channel}_res-{res_label}_desc-stacking_volume.nii.gz"
        else:
            filename = f"{subject_dir.name}_{channel}_desc-stacking_volume.nii.gz"

        return out_dir / filename

    @staticmethod
    def load_slice_metadata(nii_paths: list[Path]) -> tuple[list[tuple[int, Path, dict]], list[str]]:
        """
        Return slices as (SliceIndex, nii_path, metadata), sorted by SliceIndex.
        """
        slices = []
        skipped = []

        for nii_path in nii_paths:
            meta, _ = bmeta.load_metadata(nii_path)
            z_index = bmeta.get_z_index(meta)

            if z_index is None:
                skipped.append(nii_path.name)
                continue

            slices.append((int(z_index), nii_path, meta))

        slices.sort(key=lambda item: item[0])
        return slices, skipped

    @staticmethod
    def get_global_slice_position_map(subject_dir: Path) -> dict[int, int]:
        """
        Build the same global Z mapping used by the 2D preprocessor:
        SliceIndex -> compact position in the 3D volume.
        """
        all_niftis = list(bm.iter_subject_niftis(subject_dir))

        unique_slice_indices = sorted({
            int(bmeta.get_z_index(bmeta.load_metadata(p)[0]))
            for p in all_niftis
            if bmeta.get_z_index(bmeta.load_metadata(p)[0]) is not None
        })

        return {
            slice_index: position
            for position, slice_index in enumerate(unique_slice_indices)
        }

    @staticmethod
    def get_reference_info(first_meta: dict) -> tuple[str, list[float]]:
        """
        Get output resolution label and X/Y pixel size from the first slice.
        """
        downsampling_factor = bmeta.get_downsampling_factor(first_meta)
        res_label = f"{int(downsampling_factor)}x"

        pixel_size = first_meta.get("PixelSize")
        if pixel_size is None:
            raise ValueError("PixelSize not found in first slice metadata")

        return res_label, [float(pixel_size[0]), float(pixel_size[1])]

    @staticmethod
    def build_centered_affine(shape: tuple[int, int, int], resolution: list[float]) -> np.ndarray:
        return np.array(
            bmeta.build_centered_affine(
                shape=shape,
                resolution=resolution,
            ),
            dtype=float,
        )

    def reorient_volume(
        self,
        volume: np.ndarray,
        resolution: list[float],
    ) -> tuple[np.ndarray, list[float]]:
        """
        Apply the requested 3D reorientation to the volume and resolution.
        """
        if bmeta.is_identity_reorientation(self.reorient):
            return volume, resolution

        transpose_axes, flip_axes = bmeta.parse_reorientation_mode(self.reorient)

        volume = np.transpose(volume, transpose_axes)

        for axis in flip_axes:
            volume = np.flip(volume, axis=axis)

        new_resolution = [resolution[old_axis] for old_axis in transpose_axes]
        return volume, new_resolution

    # -------------------------------------------------------------------------
    # Validation helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def check_no_duplicate_slice_index_with_different_resolution(
        slices: list[tuple[int, Path, dict]]
    ) -> None:
        """
        A 3D volume has one voxel resolution.
        If the same SliceIndex appears twice with different PixelSize, stacking is ambiguous.
        """
        seen: dict[int, tuple[Path, tuple[float, float] | None]] = {}

        for z_index, nii_path, meta in slices:
            pixel_size = meta.get("PixelSize")

            pixel_size_key = None
            if pixel_size is not None:
                pixel_size_key = (
                    round(float(pixel_size[0]), 6),
                    round(float(pixel_size[1]), 6),
                )

            if z_index not in seen:
                seen[z_index] = (nii_path, pixel_size_key)
                continue

            old_path, old_pixel_size_key = seen[z_index]

            if old_pixel_size_key != pixel_size_key:
                raise ValueError(
                    "\nDUPLICATE SLICE INDEX WITH DIFFERENT RESOLUTION\n"
                    f"SliceIndex: {z_index}\n"
                    f"File 1: {old_path.name}, PixelSize={old_pixel_size_key}\n"
                    f"File 2: {nii_path.name}, PixelSize={pixel_size_key}\n"
                    "You cannot stack these two files in the same 3D volume.\n"
                    "Create separate volumes or resample to a common resolution first."
                )

    @staticmethod
    def keep_first_slice_per_index(
        slices: list[tuple[int, Path, dict]]
    ) -> list[tuple[int, Path, dict]]:
        """
        If exact duplicates exist, keep the first one to avoid silently overwriting a Z plane.
        """
        filtered = []
        used = set()

        for z_index, nii_path, meta in slices:
            if z_index in used:
                continue

            filtered.append((z_index, nii_path, meta))
            used.add(z_index)

        return filtered

    @staticmethod
    def check_same_2d_shape(
        slices: list[tuple[int, Path, dict]],
        expected_shape: tuple[int, int],
    ) -> None:
        """
        The current stacking code assumes all 2D preprocessed slices have the same padded shape.
        """
        for _, nii_path, _ in slices:
            data_shape = np.squeeze(nb.load(str(nii_path)).get_fdata()).shape

            if tuple(data_shape) != tuple(expected_shape):
                raise ValueError(
                    "\nINCONSISTENT 2D SHAPE IN SAME VOLUME\n"
                    f"Expected shape: {expected_shape}\n"
                    f"File: {nii_path.name}\n"
                    f"Found shape: {data_shape}\n"
                    "Run/fix the 2D preprocessing padding before stacking."
                )

    # -------------------------------------------------------------------------
    # Output metadata
    # -------------------------------------------------------------------------

    def write_output_json(
        self,
        output_nii_path: Path,
        affine: np.ndarray,
        volume_shape: tuple[int, int, int],
    ) -> None:
        meta = {
            "VolumeReorientationMode": self.reorient,
            "VolumeShape": [int(v) for v in volume_shape],
            "VoxelResolution": [
                float(affine[0, 0]),
                float(affine[1, 1]),
                float(affine[2, 2]),
            ],
            "AffineMatrix": affine.tolist(),
            "OriginalThickness": self.original_thickness,
        }

        output_json = bmeta.get_json_path(output_nii_path)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)

    # -------------------------------------------------------------------------
    # Main build functions
    # -------------------------------------------------------------------------

    def build_one_volume(self, subject_dir: Path, channel: str, nii_paths: list[Path]) -> Path:
        if not nii_paths:
            raise ValueError(f"NO SLICE FOUND FOR {subject_dir.name} {channel}")

        slices, skipped = self.load_slice_metadata(nii_paths)

        if skipped:
            self.log("WARNING skipped slices without SliceIndex:", skipped[:10])

        if not slices:
            raise ValueError(f"NO VALID SLICE INDEX FOUND FOR {subject_dir.name} {channel}")

        self.check_no_duplicate_slice_index_with_different_resolution(slices)
        slices = self.keep_first_slice_per_index(slices)

        first_z, first_path, first_meta = slices[0]
        res_label, xy_resolution = self.get_reference_info(first_meta)

        first_img = nb.load(str(first_path))
        first_data = np.squeeze(first_img.get_fdata())
        width, height = first_data.shape

        self.check_same_2d_shape(slices, expected_shape=(width, height))

        slice_position_map = self.get_global_slice_position_map(subject_dir)
        nb_slices = len(slice_position_map)

        if nb_slices == 0:
            raise ValueError(f"NO GLOBAL SLICE INDEX FOUND FOR {subject_dir.name}")

        resolution = [
            xy_resolution[0],
            xy_resolution[1],
            self.original_thickness,
        ]

        volume = np.zeros((width, height, nb_slices), dtype=np.float32)

        for z_index, nii_path, _ in slices:
            slice_position = slice_position_map[z_index]

            self.log(
                "DEBUG STACK",
                nii_path.name,
                "SliceIndex=", z_index,
                "slice_position=", slice_position,
                "nb_slices=", nb_slices,
            )

            data_2d = np.squeeze(nb.load(str(nii_path)).get_fdata())
            volume[:, :, slice_position] = data_2d

        volume, resolution = self.reorient_volume(volume, resolution)

        volume_shape = tuple(int(v) for v in volume.shape)
        affine = self.build_centered_affine(volume_shape, resolution)

        out_img = nb.Nifti1Image(volume, affine)
        out_img.set_sform(affine, code=1)
        out_img.set_qform(affine, code=1)
        out_img.header.set_xyzt_units("micron")

        out_path = self.output_path(subject_dir, channel, res_label)
        nb.save(out_img, str(out_path))
        self.write_output_json(out_path, affine, volume_shape)

        return out_path

    def build_all_volumes(self) -> None:
        for subject_dir in bm.iter_subject_dirs(self.preproc_root):
            groups = bm.group_subject_niftis_by_channel(subject_dir)

            for channel, nii_paths in groups.items():
                out = self.build_one_volume(subject_dir, channel, nii_paths)
                print("VOLUME:", out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build 3D volumes from 2D preprocessed microscopy slices."
    )

    parser.add_argument(
        "--bids_root",
        required=True,
        help="Path to BIDS root folder",
    )

    parser.add_argument(
        "--res",
        required=True,
        help="Resolution label to stack, for example 4x or 8x",
    )

    parser.add_argument(
        "--reorient",
        default="none",
        help="3D volume reorientation, for example: none or x,-z,-y",
    )

    parser.add_argument(
        "--original_thickness",
        type=float,
        default=200,
        help="Histological section thickness in micrometers",
    )

    parser.add_argument(
        "--no_debug",
        action="store_true",
        help="Disable per-slice DEBUG STACK messages",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("\nRunning VolumeBuilder3D...")

    builder = VolumeBuilder3D(
        bids_root=args.bids_root,
        original_thickness=args.original_thickness,
        reorient=args.reorient,
        res_label=args.res,
        debug=not args.no_debug,
    )

    builder.build_all_volumes()


if __name__ == "__main__":
    main()


"""
Example:

python mimosa_stacking_2D_2_3D-2.py \
  --bids_root /envau/work/nit/users/boudlal.h/BIDS-una \
  --res 8x \
  --reorient x,-z,-y \
  --original_thickness 100
"""
