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
            self.preproc_root = self.bids_root / "derivatives" / "2D-preproc"
            self.stacking_root = self.bids_root / "derivatives" / "3D-stacking"
        else:
            self.preproc_root = self.bids_root / "derivatives" / f"2D-preproc_res-{self.res_label}"
            self.stacking_root = self.bids_root / "derivatives" / f"3D-stacking_res-{self.res_label}"
                
    def build_volume_output_path(
        self,
        subject_dir: Path,
        channel: str,
        res_label: str | None = None,
    ) -> Path:
        output_dir = self.stacking_root / subject_dir.name / "micr"
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
    """
    def reorient_existing_sform(
        self,
        sform: np.ndarray,
        old_shape: tuple[int, int, int],
        old_resolution: list[float],
        ) -> np.ndarray:
        mode = self.reorient

        if VolumeBuilder3D.is_identity_reorientation(mode):
            return sform

        old_affine = VolumeBuilder3D.build_new_affine_matrix(
            old_shape,
            old_resolution,
        )

        new_shape, new_resolution = self.reorient_shape_and_resolution(
            shape=old_shape,
            resolution=old_resolution,
            mode=mode,
        )

        new_affine = VolumeBuilder3D.build_new_affine_matrix(
            new_shape,
            new_resolution,
        )

        transform = new_affine @ np.linalg.inv(old_affine)

        return transform @ sform
    def update_2d_sforms_after_reorientation(self, root_2d: Path) -> None:
        mode = self.reorient

        if VolumeBuilder3D.is_identity_reorientation(mode):
            print(f"No volume reorientation requested for {root_2d.name} — keeping existing 2D SFormMatrix.")
            return

        if not root_2d.exists():
            return

        for subject_dir in bm.iter_subject_dirs(root_2d):
            nii_paths = list(bm.iter_subject_niftis(subject_dir))

            if not nii_paths:
                continue

            unique_slice_indices = sorted({
                int(bmeta.get_z_index(bmeta.load_metadata(p)[0]))
                for p in nii_paths
                if bmeta.get_z_index(bmeta.load_metadata(p)[0]) is not None
            })

            nb_slices = len(unique_slice_indices)

            if nb_slices == 0:
                continue

            for nii_path in nii_paths:
                meta, _ = bmeta.load_metadata(nii_path)

                if "SFormMatrix" not in meta:
                    print(f"WARNING: no SFormMatrix in {nii_path.name}, skipping")
                    continue

                if meta.get("SFormVolumeReorientationMode") == self.reorient:
                    continue

                source_sform = meta.get("InitialSFormMatrix", meta["SFormMatrix"])
                sform = np.array(source_sform, dtype=float)

                img = nb.load(str(nii_path))
                data_shape = np.squeeze(img.get_fdata()).shape

                width = int(data_shape[0])
                height = int(data_shape[1])

                res_x = float(np.linalg.norm(sform[:3, 0]))
                res_y = float(np.linalg.norm(sform[:3, 1]))
                res_z = float(np.linalg.norm(sform[:3, 2]))

                if res_z == 0:
                    res_z = float(self.original_thickness)

                old_shape = (width, height, nb_slices)
                old_resolution = [res_x, res_y, res_z]

                new_sform = self.reorient_existing_sform(
                    sform=sform,
                    old_shape=old_shape,
                    old_resolution=old_resolution,
                )

                bmeta.write_sform_to_nifti_and_json(
                    nii_path=nii_path,
                    sform_matrix=new_sform,
                    description=f"SFormMatrix updated using reorient={self.reorient}",
                    reorient=self.reorient,
                )

                print(f"Updated SFormMatrix: {nii_path.name}")
    """

    def build_one_volume(self, subject_dir: Path, channel: str, nii_paths: list[Path]) -> Path:
        if not nii_paths:
            raise ValueError(f"NO SLICE FOUND FOR  {subject_dir.name} {channel}")

        #  Lire les métadonnées de toutes les slices et trier selon Z
        sorted_slices = []
        skipped_slices = []

        for nii_path in nii_paths:
            meta, _ = bmeta.load_metadata(nii_path)
            z_index = bmeta.get_z_index(meta)

            if z_index is None:
                skipped_slices.append(nii_path.name)
                continue

            sorted_slices.append((z_index, nii_path, meta))
        sorted_slices.sort(key=lambda x: x[0])

        if not sorted_slices:
            raise ValueError(f"NO VALID SLICE INDEX FOUND FOR {subject_dir.name} {channel}")        
        # Métadonnées de référence (première slice du groupe)
        first_meta = sorted_slices[0][2]
        downsampling_factor = bmeta.get_downsampling_factor(first_meta)
        print("dowsnamplkungvegdfhrfhbhrfb",downsampling_factor)
        original_res = bmeta.get_original_resolution(first_meta)
        res_label = f"{int(downsampling_factor)}x"
        downsampled_res = original_res * downsampling_factor

        #  Lire la taille des slices déjà paddées/réorientées
        first_img = nb.load(str(sorted_slices[0][1]))
        first_data = np.squeeze(first_img.get_fdata())

        width = first_data.shape[0]
        height = first_data.shape[1]
        nb_slices = len(sorted_slices)

        volume_shape = np.array((width, height, nb_slices))

        #  Construire la résolution et l’affine du volume final
        new_resolution = [downsampled_res, downsampled_res, self.original_thickness]

        # float32 instead of default float64 to reduce memory usage by half
        # (4 bytes vs 8 bytes per pixel) — float32 precision is sufficient for microscopy images
        # which have pixel values between 0 and 65535
        stack_of_slices = np.zeros((width, height, nb_slices), dtype=np.float32) 
        for i, (z_index, nii_path, meta) in enumerate(sorted_slices):
            print(
                "DEBUG STACK",
                nii_path.name,
                "SliceIndex=", z_index,
                "volume_position=", i,
                "nb_slices=", len(sorted_slices),
            )
            img = nb.load(str(nii_path))
            data = img.get_fdata()
            data_2d = np.squeeze(data)
            stack_of_slices[:, :, i] = data_2d

        stack_of_slices, new_resolution = self.reorient_volume_3d(stack_of_slices,new_resolution,self.reorient)
        volume_shape = np.array(stack_of_slices.shape)

        new_affine = VolumeBuilder3D.build_new_affine_matrix(tuple(volume_shape),new_resolution)

        # Sauvegarder le volume
        out_img = nb.Nifti1Image(stack_of_slices, new_affine)
        out_img.set_sform(new_affine, code=1)
        out_img.set_qform(new_affine, code=1)
        out_img.header.set_xyzt_units("micron")
        output_path = self.build_volume_output_path(subject_dir, channel, res_label)
        nb.save(out_img, str(output_path))
        output_json = bmeta.get_json_path(output_path)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump({}, f)
        self.update_output_json(output_path, new_affine, tuple(volume_shape))
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
    builder.update_2d_sforms_after_reorientation(
        builder.bids_root / "derivatives" / f"2D-downsampled_res-{builder.res_label}"
    )

    builder.update_2d_sforms_after_reorientation(
        builder.preproc_root
    )
"""

"""
python mimosa_stacking_2D_2_3D-2.py \
  --bids_root /envau/work/nit/users/boudlal.h/BIDS-una \
  --res 4x \
  --reorient x,-z,-y \
  --original_thickness 100
"""