
import os
import sys
import json
import numpy as np
import nibabel as nb

from pathlib import Path

_ROOT = os.path.abspath(os.path.dirname(__file__))
while (
    _ROOT != os.path.dirname(_ROOT)
    and not os.path.isdir(os.path.join(_ROOT, "core"))
):
    _ROOT = os.path.dirname(_ROOT)

sys.path.insert(0, _ROOT)

from core.bids import bids_metadata as bmeta
from core.bids import bids_manager as bm


class VolumeBuilder3D:

    def __init__(
        self,
        bids_root: str,
        original_thickness: float,
        reorient: str = "none",
        res_label: str = None,
    ):

        self.bids_root = Path(bids_root).resolve()
        self.original_thickness = original_thickness
        self.reorient = reorient
        self.res_label = res_label

        if self.res_label is None:
            raise ValueError("res_label is required")

        self.preproc_root = (
            self.bids_root / "derivatives" / "2D" / "padded"
        )

        self.stacking_root = (
            self.bids_root / "derivatives" / "3D" / "stacking"
        )

        self.stacking_root.mkdir(
            parents=True,
            exist_ok=True
        )

    def build_volume_output_path(
        self,
        subject_dir,
        channel,
        res_label=None,
    ):

        output_dir = (
            self.stacking_root
            / subject_dir.name
            / "micr"
            / f"res-{res_label}"
        )

        output_dir.mkdir(parents=True, exist_ok=True)

        return (
            output_dir
            / f"{subject_dir.name}_{channel}_res-{res_label}_volume.nii.gz"
        )

    @staticmethod
    def get_valid_affine(img, path=None):

        sform, sform_code = img.get_sform(coded=True)

        if sform is not None and sform_code > 0:
            return np.asarray(sform, dtype=float)

        qform, qform_code = img.get_qform(coded=True)

        if qform is not None and qform_code > 0:
            return np.asarray(qform, dtype=float)

        if img.affine is not None:
            return np.asarray(img.affine, dtype=float)

        raise ValueError(f"No valid affine found in {path}")

    @staticmethod
    def print_orientation_diagnostics(nii_paths):

        print("\n========== ORIENTATION DIAGNOSTICS ==========")

        for path in nii_paths:

            img = nb.load(str(path))
            affine = VolumeBuilder3D.get_valid_affine(img, path)

            print("\nFile:", path.name)
            print("Shape:", img.shape)
            print("Orientation:", nb.aff2axcodes(affine))
            print("Affine:\n", affine)

        print("\n=============================================\n")

    @staticmethod
    def harmonize_slice_orientation(
        img,
        reference_affine,
        reference_shape,
        path=None,
    ):

        affine = VolumeBuilder3D.get_valid_affine(img, path)

        reference_orientation = nb.aff2axcodes(reference_affine)
        current_orientation = nb.aff2axcodes(affine)

        data = np.asarray(img.get_fdata(), dtype=np.float32)
        data = np.squeeze(data)

        if data.ndim != 2:
            raise ValueError(
                f"Expected 2D data in {path}: {data.shape}"
            )

        corrected_affine = affine.copy()

        if current_orientation[1:] != reference_orientation[1:]:
            raise ValueError(
                f"Incompatible orientations in {path.name}: "
                f"reference={reference_orientation}, "
                f"current={current_orientation}"
            )

        if current_orientation[0] != reference_orientation[0]:

            if set(current_orientation[:1] + reference_orientation[:1]) != {"L", "R"}:
                raise ValueError(
                    f"Unsupported orientation difference in {path.name}"
                )

            print(
                f"FLIPPING X: {path.name} "
                f"{current_orientation} -> {reference_orientation}"
            )

            old_x_column = affine[:3, 0].copy()

            data = np.flip(data, axis=0).copy()

            corrected_affine[:3, 0] *= -1.0

            corrected_affine[:3, 3] += (
                old_x_column * (data.shape[0] - 1)
            )

        corrected_orientation = nb.aff2axcodes(corrected_affine)

        if corrected_orientation != reference_orientation:
            raise ValueError(
                f"Orientation correction failed in {path.name}"
            )

        if data.shape != reference_shape:
            raise ValueError(
                f"Shape mismatch in {path.name}: "
                f"{data.shape} vs {reference_shape}"
            )

        if not np.allclose(
            corrected_affine[:3, :2],
            reference_affine[:3, :2],
            atol=1e-4,
            rtol=1e-5,
        ):
            raise ValueError(
                f"Incompatible in-plane affine in {path.name}"
            )

        return data.astype(np.float32), corrected_affine
        
        
    @staticmethod
    def verify_slice_position(
        affine,
        reference_affine,
        slice_position,
        reference_position,
        path,
        tolerance=0.01,
    ):

        expected_origin = (
            reference_affine[:3, 3]
            + (
                slice_position - reference_position
            ) * reference_affine[:3, 2]
        )

        actual_origin = affine[:3, 3]

        if not np.allclose(
            actual_origin,
            expected_origin,
            atol=tolerance,
            rtol=0,
        ):
            raise ValueError(
                f"Physical position mismatch in {path.name}:\n"
                f"Expected: {expected_origin}\n"
                f"Actual: {actual_origin}"
            )

    def reorient_volume_3d(self, volume, resolution, mode):

        if bmeta.is_identity_reorientation(mode):
            return volume, resolution

        transpose_axes, flip_axes = (
            bmeta.parse_reorientation_mode(mode)
        )

        volume = np.transpose(volume, transpose_axes)

        for axis in flip_axes:
            volume = np.flip(volume, axis=axis)

        new_resolution = [
            resolution[old_axis]
            for old_axis in transpose_axes
        ]

        return volume, new_resolution

    @staticmethod
    def reorient_affine_like_data(affine, old_shape, mode):

        affine = np.asarray(affine, dtype=float)

        if bmeta.is_identity_reorientation(mode):
            return affine.copy()

        transpose_axes, flip_axes = (
            bmeta.parse_reorientation_mode(mode)
        )

        new_affine = np.eye(4)

        for new_axis, old_axis in enumerate(transpose_axes):

            col = affine[:3, old_axis].copy()

            if new_axis in flip_axes:
                col *= -1.0

            new_affine[:3, new_axis] = col

        new_affine[:3, 3] = affine[:3, 3].copy()

        for new_axis, old_axis in enumerate(transpose_axes):

            if new_axis in flip_axes:
                new_affine[:3, 3] += (
                    affine[:3, old_axis]
                    * (old_shape[old_axis] - 1)
                )

        return new_affine

    def update_output_json(
        self,
        output_nii_path,
        new_affine,
        volume_shape,
    ):

        meta, output_json = bmeta.load_metadata(output_nii_path)

        meta["VolumeReorientationMode"] = self.reorient
        meta["VolumeShape"] = [int(v) for v in volume_shape]

        meta["VoxelResolution"] = [
            float(np.linalg.norm(new_affine[:3, i]))
            for i in range(3)
        ]

        meta["AffineMatrix"] = new_affine.tolist()
        meta["OriginalThickness"] = self.original_thickness
        meta["VoxelResolutionUnits"] = "mm"

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)

    def build_one_volume(self, subject_dir, channel, nii_paths):

        if not nii_paths:
            raise ValueError(
                f"NO SLICE FOUND FOR {subject_dir.name} {channel}"
            )

        self.print_orientation_diagnostics(nii_paths)

        sorted_slices = []
        skipped_slices = []

        for nii_path in nii_paths:

            meta, _ = bmeta.load_metadata(nii_path)

            slice_index = bmeta.get_z_index(meta)
            slice_position = meta.get("SlicePosition")

            if slice_index is None:
                skipped_slices.append(
                    f"{nii_path.name}: missing SliceIndex"
                )
                continue

            if slice_position is None:
                skipped_slices.append(
                    f"{nii_path.name}: missing SlicePosition"
                )
                continue

            sorted_slices.append(
                (
                    int(slice_position),
                    int(slice_index),
                    nii_path,
                    meta,
                )
            )

        if skipped_slices:
            print("WARNING: skipped slices:")
            for item in skipped_slices:
                print("  -", item)

        if not sorted_slices:
            raise ValueError(
                f"NO VALID SLICE POSITION FOUND FOR {subject_dir.name}"
            )

        sorted_slices.sort(key=lambda x: x[0])

        first_meta = sorted_slices[0][3]

        pixel_size = first_meta.get("PixelSize")

        if pixel_size is None:
            raise ValueError("PixelSize missing")

        downsampled_res_x = float(pixel_size[0])
        downsampled_res_y = float(pixel_size[1])

        nb_slices = first_meta.get("NumberOfSlices")

        if nb_slices is None:
            raise ValueError("NumberOfSlices missing")

        nb_slices = int(nb_slices)

        disagreeing = [
            (p.name, int(m["NumberOfSlices"]))
            for _, _, p, m in sorted_slices
            if m.get("NumberOfSlices") is not None
            and int(m["NumberOfSlices"]) != nb_slices
        ]

        if disagreeing:
            raise ValueError(
                f"Inconsistent NumberOfSlices: {disagreeing[:5]}"
            )

        reference_slice = min(
            sorted_slices,
            key=lambda item: item[1]
        )

        reference_position = int(reference_slice[0])
        reference_path = reference_slice[2]

        reference_img = nb.load(str(reference_path))

        reference_affine = self.get_valid_affine(
            reference_img,
            reference_path
        )

        print("\nREFERENCE:", reference_path.name)
        print("ORIENTATION:", nb.aff2axcodes(reference_affine))

        reference_data = np.squeeze(reference_img.get_fdata())

        if reference_data.ndim != 2:
            raise ValueError(
                f"Invalid reference shape: {reference_data.shape}"
            )

        width, height = reference_data.shape

        old_volume_shape = (width, height, nb_slices)

        stack_of_slices = np.zeros(
            old_volume_shape,
            dtype=np.float32
        )

        new_resolution = [
            downsampled_res_x,
            downsampled_res_y,
            float(self.original_thickness),
        ]

        filled_positions = set()

        for (
            slice_position,
            slice_index,
            nii_path,
            meta,
        ) in sorted_slices:

            if slice_position < 0 or slice_position >= nb_slices:
                raise ValueError(
                    f"Invalid SlicePosition={slice_position} "
                    f"in {nii_path.name}"
                )

            #if slice_position in filled_positions:
            #    raise ValueError(
            #        f"Duplicate SlicePosition={slice_position}"
            #    )

            img = nb.load(str(nii_path))

            data_2d, corrected_affine = (
                self.harmonize_slice_orientation(
                    img=img,
                    reference_affine=reference_affine,
                    reference_shape=(width, height),
                    path=nii_path,
                )
            )

            self.verify_slice_position(
                affine=corrected_affine,
                reference_affine=reference_affine,
                slice_position=slice_position,
                reference_position=reference_position,
                path=nii_path,
            )

            stack_of_slices[:, :, slice_position] = data_2d

            filled_positions.add(slice_position)

        missing_positions = sorted(
            set(range(nb_slices)) - filled_positions
        )

        if missing_positions:
            print(
                f"WARNING: missing slices: {missing_positions}"
            )

        reference_affine = reference_affine.copy()

        reference_affine[:3, 3] -= (
            reference_position * reference_affine[:3, 2]
        )

        stack_of_slices, new_resolution = (
            self.reorient_volume_3d(
                stack_of_slices,
                new_resolution,
                self.reorient,
            )
        )

        final_volume_shape = tuple(
            int(v) for v in stack_of_slices.shape
        )

        new_affine = self.reorient_affine_like_data(
            affine=reference_affine,
            old_shape=old_volume_shape,
            mode=self.reorient,
        )

        

        print("\nFINAL SHAPE:", final_volume_shape)
        print("FINAL AFFINE:")
        print(new_affine)

        out_img = nb.Nifti1Image(
            stack_of_slices,
            new_affine
        )

        out_img.set_sform(new_affine, code=1)
        out_img.set_qform(new_affine, code=1)
        out_img.header.set_xyzt_units("mm")

        output_path = self.build_volume_output_path(
            subject_dir,
            channel,
            self.res_label
        )

        nb.save(out_img, str(output_path))

        output_json = bmeta.get_json_path(output_path)

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump({}, f)

        self.update_output_json(
            output_path,
            new_affine,
            final_volume_shape
        )

        print("\nVOLUME CREATED:", output_path)

        return output_path

    def build_all_volumes(self):

        if not self.preproc_root.exists():
            print(
                f"ERROR: input path not found: {self.preproc_root}"
            )
            return

        found_any = False

        for subject_dir in bm.iter_subject_dirs(
            self.preproc_root
        ):

            groups = bm.group_subject_niftis_by_channel(
                subject_dir
            )

            for channel, nii_paths in groups.items():

                nii_paths = [
                    p for p in nii_paths
                    if f"_res-{self.res_label}_" in p.name
                ]

                if not nii_paths:
                    continue

                found_any = True

                output = self.build_one_volume(
                    subject_dir,
                    channel,
                    nii_paths
                )

                print("VOLUME:", output)

        if not found_any:
            print(
                f"No NIfTI found for res-{self.res_label}"
            )


if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description="3D volume stacking from 2D padded slices"
    )

    parser.add_argument(
        "-bids_root",
        required=True,
        help="Path to BIDS root folder"
    )

    parser.add_argument(
        "-res",
        required=True,
        help="Resolution label, for example 8x"
    )

    parser.add_argument(
        "-reorient",
        default="none"
    )

    parser.add_argument(
        "-original_thickness",
        type=float,
        default=200
    )

    args = parser.parse_args()

    print("\nRunning VolumeBuilder3D...")

    builder = VolumeBuilder3D(
        bids_root=args.bids_root,
        original_thickness=args.original_thickness,
        reorient=args.reorient,
        res_label=args.res,
    )

    builder.build_all_volumes()
      

