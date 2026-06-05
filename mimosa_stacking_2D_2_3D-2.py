import numpy as np
import nibabel as nb
from pathlib import Path
import json 
from BIDS import bids_metadata as bmeta
from BIDS import bids_manager as bm



class VolumeBuilder3D:
    def __init__(self, bids_root: str, original_thickness: float, reorient: str="none",res_label: str = None,):
        self.bids_root = Path(bids_root).resolve()
        self.original_thickness = original_thickness
        self.reorient = reorient
        self.res_label = res_label

        if self.res_label is None:
            raise ValueError("res_label is required")
        else:
            self.preproc_root  = self.bids_root / "derivatives" / "2D" / "padded" / f"res-{self.res_label}"
            self.stacking_root = self.bids_root / "derivatives" / "3D" / "stacking"
                
    def build_volume_output_path(
        self,
        subject_dir: Path,
        channel: str,
        res_label: str | None = None,
    ) -> Path:
        output_dir = self.stacking_root / subject_dir.name / "micr" / f"res-{res_label}"
        output_dir.mkdir(parents=True, exist_ok=True)

        if res_label is not None:
            return output_dir / f"{subject_dir.name}_{channel}_res-{res_label}_desc-stacking_volume.nii.gz"

        return output_dir / f"{subject_dir.name}_{channel}_desc-stacking_volume.nii.gz"
        
    def update_output_json(self, output_nii_path: Path, new_affine: np.ndarray, volume_shape: tuple[int, int, int]) -> None:
        """
        Update JSON sidecar for 3D volume with stacking metadata
        """

        meta, output_json = bmeta.load_metadata(output_nii_path)
        meta["VolumeReorientationMode"] = self.reorient
        meta["VolumeShape"] = [
            int(volume_shape[0]),
            int(volume_shape[1]),
            int(volume_shape[2]),
        ]

        meta["VoxelResolution"] = [
            float(new_affine[0, 0]),
            float(new_affine[1, 1]),
            float(new_affine[2, 2]),
        ]

        meta["AffineMatrix"] = new_affine.tolist()

        meta["OriginalThickness"] = self.original_thickness

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)
    
    
    
    def reorient_volume_3d(
        self,
        volume: np.ndarray,
        resolution: list[float],
        mode: str,
    ) -> tuple[np.ndarray, list[float]]:
        """
        Reorient a 3D volume using the parsed reorientation mode.
        """
        if bmeta.is_identity_reorientation(mode):
            return volume, resolution

        transpose_axes, flip_axes = bmeta.parse_reorientation_mode(mode)

        volume = np.transpose(volume, transpose_axes)

        for axis in flip_axes:
            volume = np.flip(volume, axis=axis)

        resolution = list(resolution)
        new_resolution = [resolution[old_axis] for old_axis in transpose_axes]

        return volume, new_resolution
    
    @staticmethod
    def build_new_affine_matrix(volume_shape: tuple[int, int, int], resolution: list[float]) -> np.ndarray:
        return np.array(
            bmeta.build_centered_affine(
                shape=volume_shape,
                resolution=resolution,
            ),
            dtype=float,
        )
    
    def build_one_volume(self, subject_dir: Path, channel: str, nii_paths: list[Path]) -> Path:
        if not nii_paths:
            raise ValueError(f"NO SLICE FOUND FOR {subject_dir.name} {channel}")

        # Read metadata for all slices.
        # We use SlicePosition from JSON, not YAML and not enumerate().
        sorted_slices = []
        skipped_slices = []

        for nii_path in nii_paths:
            meta, _ = bmeta.load_metadata(nii_path)

            slice_index = bmeta.get_z_index(meta)
            slice_position = meta.get("SlicePosition")

            if slice_index is None:
                skipped_slices.append(f"{nii_path.name}: missing SliceIndex")
                continue

            if slice_position is None:
                skipped_slices.append(f"{nii_path.name}: missing SlicePosition")
                continue

            sorted_slices.append((int(slice_position), int(slice_index), nii_path, meta))

        if skipped_slices:
            print("WARNING: skipped slices:")
            for item in skipped_slices:
                print(f"  - {item}")

        if not sorted_slices:
            raise ValueError(f"NO VALID SLICE POSITION FOUND FOR {subject_dir.name} {channel}")

        sorted_slices.sort(key=lambda x: x[0])

        # Reference metadata from first valid slice.
        first_meta = sorted_slices[0][3]

        downsampling_factor = bmeta.get_downsampling_factor(first_meta)
        res_label = f"{int(downsampling_factor)}x"

        pixel_size = first_meta.get("PixelSize")
        if pixel_size is None:
            raise ValueError(f"PixelSize not found in metadata for {sorted_slices[0][2].name}")

        downsampled_res_x = float(pixel_size[0])
        downsampled_res_y = float(pixel_size[1])

        # NumberOfSlices must come from JSON.
        # This is written during the converter step from the YAML once.
        nb_slices = first_meta.get("NumberOfSlices")
        if nb_slices is None:
            raise ValueError(
                f"NumberOfSlices missing in {sorted_slices[0][2].name}. "
                "Run the converter again so JSON sidecars contain NumberOfSlices."
            )

        nb_slices = int(nb_slices)

        # Read the size of preprocessed padded slices.
        first_img = nb.load(str(sorted_slices[0][2]))
        first_data = np.squeeze(first_img.get_fdata())

        width = int(first_data.shape[0])
        height = int(first_data.shape[1])

        volume_shape = (width, height, nb_slices)

        # Allocate the full volume using NumberOfSlices.
        # Some slice positions may remain empty if missing in this channel.
        stack_of_slices = np.zeros(volume_shape, dtype=np.float32)

        new_resolution = [
            downsampled_res_x,
            downsampled_res_y,
            float(self.original_thickness),
        ]

        filled_positions = set()

        for slice_position, slice_index, nii_path, meta in sorted_slices:
            if slice_position < 0 or slice_position >= nb_slices:
                raise ValueError(
                    f"Invalid SlicePosition={slice_position} in {nii_path.name}. "
                    f"Expected value between 0 and {nb_slices - 1}."
                )

            if slice_position in filled_positions:
                raise ValueError(
                    f"Duplicate SlicePosition={slice_position} for channel {channel} "
                    f"in subject {subject_dir.name}."
                )

            img = nb.load(str(nii_path))
            data_2d = np.squeeze(img.get_fdata()).astype(np.float32)

            if data_2d.shape != (width, height):
                raise ValueError(
                    f"Shape mismatch in {nii_path.name}: got {data_2d.shape}, "
                    f"expected {(width, height)}. Make sure preprocessing padded all slices "
                    "to the same target shape."
                )

            stack_of_slices[:, :, slice_position] = data_2d
            filled_positions.add(slice_position)

        missing_positions = sorted(set(range(nb_slices)) - filled_positions)
        if missing_positions:
            print(
                f"WARNING: {len(missing_positions)} empty slice positions for "
                f"{subject_dir.name} {channel}: {missing_positions[:20]}"
                + (" ..." if len(missing_positions) > 20 else "")
            )

        # Apply the requested 3D reorientation to the actual volume.
        stack_of_slices, new_resolution = self.reorient_volume_3d(
            stack_of_slices,
            new_resolution,
            self.reorient,
        )

        final_volume_shape = tuple(int(v) for v in stack_of_slices.shape)

        # Build the affine in the same centered common reference.
        new_affine = VolumeBuilder3D.build_new_affine_matrix(
            final_volume_shape,
            new_resolution,
        )

        # Save the 3D volume.
        out_img = nb.Nifti1Image(stack_of_slices, new_affine)
        out_img.set_sform(new_affine, code=1)
        out_img.set_qform(new_affine, code=1)
        out_img.header.set_xyzt_units("micron")

        output_path = self.build_volume_output_path(subject_dir, channel, res_label)
        nb.save(out_img, str(output_path))

        # Create JSON sidecar and update it.
        output_json = bmeta.get_json_path(output_path)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump({}, f)

        self.update_output_json(output_path, new_affine, final_volume_shape)

        return output_path
        
    def build_all_volumes(self):
        for subject_dir in bm.iter_subject_dirs(self.preproc_root):
            groups = bm.group_subject_niftis_by_channel(subject_dir)

            for channel, nii_paths in groups.items():
                out = self.build_one_volume(subject_dir, channel, nii_paths)
                print("VOLUME:", out)
    
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="3D volume stacking from 2D preprocessed slices")
    parser.add_argument(
        "--bids_root",
        required=True,
        help="Path to BIDS root folder"
    )
    parser.add_argument(
        "--res",
        required=True,
        help="Resolution label to stack, for example 4x"
    )
    parser.add_argument(
        "--reorient",
        required=False,
        default="none",
        help="3D volume reorientation: none, x,y,z, x,-z,-y, swap_yz+flip_y+flip_z, etc."
    )
    parser.add_argument(
        "--original_thickness",
        required=False,
        type=float,
        default=200,
        help="Histological section thickness"
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

   
"""
python mimosa_stacking_2D_2_3D-2.py \
  --bids_root /envau/work/nit/users/boudlal.h/BIDS-una \
  --res 4x \
  --reorient x,-z,-y \
  --original_thickness 100
"""