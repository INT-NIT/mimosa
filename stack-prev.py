import numpy as np
import nibabel as nb
from pathlib import Path
import json 
from BIDS import bids_metadata as bmeta
from BIDS import bids_manager as bm

class SlicePreprocessor:
    def __init__(
        self,input_root: str,output_root: str,original_thickness: float,volume_reorient: str = "none",):     
        self.input_root = Path(input_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.original_thickness = original_thickness
        self.volume_reorient = volume_reorient
        self.subject_max_sizes = {} # having track of max width and height for each subject 

        self.downsampled_root = self.input_root / "derivatives" / "2D-downsampled"
        self.preproc_root = self.output_root / "derivatives" / "2D-preproc"

        if not self.downsampled_root.exists():
            raise FileNotFoundError(f"Repository not found : {self.downsampled_root}")

        self.preproc_root.mkdir(parents=True, exist_ok=True)

    def build_output_path(self, nii_path: Path) -> Path:
        """
        preserve same hierarchy of derivatives/downsampled  in derivatives/preproc 
        """
        relative_path = nii_path.relative_to(self.downsampled_root)
        output_path = self.preproc_root / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    def get_slice_size_from_json(self, nii_path: Path) -> tuple[int, int]:
        """
            Read width and height of one slice from its JSON sidecar
        """
        meta, json_path=bmeta.load_metadata(nii_path)
        width = meta.get("Width")
        height = meta.get("Height")

        if width is None or height is None:
            raise ValueError(f"Width/Height NOT FOUND IN {json_path}")

        return int(width), int(height)              
    
    def compute_target_shape(self, nii_paths, padding_delta, subject_name):
        max_width = 0
        max_height = 0

        for nii_path in nii_paths:
            width, height = self.get_slice_size_from_json(nii_path)

            if width > max_width:
                max_width = width
            if height > max_height:
                max_height = height

        self.subject_max_sizes[subject_name] = (max_width, max_height)

        return max_width + padding_delta, max_height + padding_delta
    
   
        
    def update_output_json(self, output_nii_path: Path, target_shape: tuple[int, int], subject_name: str) -> None:
        """
        Update copied JSON sidecar with preprocessing metadata
        """
        meta, output_json = bmeta.load_metadata(output_nii_path)

        meta["PaddingTargetShape"] = [int(target_shape[0]), int(target_shape[1])]
        meta["SubjectMaxSize"] = [
            int(self.subject_max_sizes[subject_name][0]),
            int(self.subject_max_sizes[subject_name][1]),
        ]

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)
    def process_one_slice(
        self,
        nii_path: Path,
        target_shape: tuple[int, int],
        subject_name: str,
        volume_affine: np.ndarray,
        old_shape: tuple[int, int, int],
        slice_position: int,
    ) -> Path:
        """
        Load one input NIfTI, pad it to target_shape,
        save it to derivatives/preproc, and copy its JSON sidecar.
        """
        output_path = self.build_output_path(nii_path)

        img = nb.load(str(nii_path))
        data = img.get_fdata()
        header = img.header.copy()

        # flip , rotation , padding works more efficienly with 2D so we squeeze 3D (X,Y,Z)=> Z=1 to just (X,Y)
        data_2d = np.squeeze(data)

        current_width = data_2d.shape[0]
        current_height = data_2d.shape[1]

        target_width, target_height = target_shape

        shift_x = target_width - current_width
        shift_y = target_height - current_height

        if shift_x < 0 or shift_y < 0:
            raise ValueError(
                f"Target shape {target_shape} smaller than the image {data_2d.shape} for {nii_path.name}"
            )

        pad_x_before = round(shift_x / 2)
        pad_y_before = round(shift_y / 2)

        downsampled_sform = self.compute_sform_matrix(
            volume_affine=volume_affine,
            old_shape=old_shape,
            slice_position=slice_position,
            pad_delta=(pad_x_before, pad_y_before),
        )

        self.write_sform_to_nifti_and_json(
            nii_path=nii_path,
            sform_matrix=downsampled_sform,
            description="SForm matrix placing this 2D downsampled slice in the final 3D volume space",
        )

        padded_data_2d = np.pad(
            data_2d,
            (
                (pad_x_before, shift_x - pad_x_before),
                (pad_y_before, shift_y - pad_y_before),
            ),
            mode="constant",
            constant_values=0,
        )

        padded_data = np.expand_dims(padded_data_2d, axis=2)

        preproc_sform = self.compute_sform_matrix(
            volume_affine=volume_affine,
            old_shape=old_shape,
            slice_position=slice_position,
            pad_delta=(0, 0),
        )

        out_img = nb.Nifti1Image(padded_data, preproc_sform, header)
        out_img.set_sform(preproc_sform, code=1)
        out_img.set_qform(preproc_sform, code=1)
        out_img.header.set_xyzt_units("micron")
        nb.save(out_img, str(output_path))

        bmeta.copy_json_sidecar(nii_path, output_path)
        self.update_output_json(output_path, target_shape, subject_name)

        self.write_sform_to_nifti_and_json(
            nii_path=output_path,
            sform_matrix=preproc_sform,
            description="SForm matrix placing this padded 2D preprocessed slice in the final 3D volume space",
        )

        return output_path

    def compute_sform_matrix(
        self,
        volume_affine: np.ndarray,
        old_shape: tuple[int, int, int],
        slice_position: int,
        pad_delta: tuple[int, int],
    ) -> np.ndarray:
        """
        Build SFormMatrix for one 2D slice.

        This matrix places a 2D slice inside the final 3D volume space.

        old_shape:
            shape before reorientation = (width, height, nb_slices)

        slice_position:
            position of this slice in the stack: 0, 1, 2, ...

        pad_before:
            for 2D-downsampled: (pad_x_before, pad_y_before)
            for 2D-preproc: (0, 0)
        """

        pad_x, pad_y = pad_delta

        # Local pixel (0,0) of the 2D image , gives indexes of the pixel/voxel 
        old_origin = (pad_x, pad_y, slice_position)
        # Local pixel (1,0): one step in image X
        old_x_step = (pad_x + 1, pad_y, slice_position)
        # Local pixel (0,1): one step in image Y
        old_y_step = (pad_x, pad_y + 1, slice_position)
        old_z_step = (pad_x, pad_y, slice_position + 1)

        # Convert old indices to final reoriented volume indices , gives the new indexes of the same previous pixel but after reorientation 
        new_origin = VolumeBuilder3D.map_old_index_to_reoriented_index(
            old_origin,
            old_shape,
            self.volume_reorient,
        )

        new_x_step = VolumeBuilder3D.map_old_index_to_reoriented_index(
            old_x_step,
            old_shape,
            self.volume_reorient,
        )

        new_y_step = VolumeBuilder3D.map_old_index_to_reoriented_index(
            old_y_step,
            old_shape,
            self.volume_reorient,
        )
        new_z_step = VolumeBuilder3D.map_old_index_to_reoriented_index(
            old_z_step,
            old_shape,
            self.volume_reorient,
        )
        # Convert voxel indices to physical coordinates using final volume affine
        new_origin = np.array([new_origin[0], new_origin[1], new_origin[2], 1.0])
        new_x_step = np.array([new_x_step[0], new_x_step[1], new_x_step[2], 1.0])
        new_y_step = np.array([new_y_step[0], new_y_step[1], new_y_step[2], 1.0])
        new_z_step = np.array([new_z_step[0], new_z_step[1], new_z_step[2], 1.0])

        origin_phys = volume_affine @ new_origin # gives how much is far away the pixel 0,0 of the 2D image from the origin of the volume which is the center  
        x_step_phys = volume_affine @ new_x_step
        y_step_phys = volume_affine @ new_y_step
        z_step_phys = volume_affine @ new_z_step

        sform = np.eye(4, dtype=float)

        # Direction when image x increases by 1 pixel
        sform[:3, 0] = x_step_phys[:3] - origin_phys[:3] # position du pixel (1,0) - position du pixel (0,0) = pixel size n thats the resolution

        # Direction when image y increases by 1 pixel
        sform[:3, 1] = y_step_phys[:3] - origin_phys[:3]

        # 2D slice has no local z direction
        sform[:3, 2] = z_step_phys[:3] - origin_phys[:3]
        
        # Position of image pixel (0,0)
        sform[:3, 3] = origin_phys[:3]

        return sform
    def reorient_existing_sform(
    self,
    sform: np.ndarray,
    old_shape: tuple[int, int, int],
    old_resolution: list[float],
) -> np.ndarray:
        """
        Apply volume_reorient to an existing SFormMatrix.

        The input sform is assumed to be in the non-reoriented centered reference.
        The output sform is in the reoriented centered reference.
        """
        mode = self.volume_reorient

        if mode is None or mode.strip().lower() in ("", "none", "no", "identity", "x,y,z"):
            return sform

        tmp_volume = np.zeros(old_shape, dtype=np.uint8)

        tmp_volume, new_resolution = self.reorient_volume_3d(
            tmp_volume,
            old_resolution,
            mode,
        )

        old_affine = VolumeBuilder3D.build_new_affine_matrix(
            old_shape,
            old_resolution,
        )

        new_affine = VolumeBuilder3D.build_new_affine_matrix(
            tuple(tmp_volume.shape),
            new_resolution,
        )

        transform = new_affine @ np.linalg.inv(old_affine)

        return transform @ sform
    def write_sform_to_nifti_and_json(
        self,
        nii_path: Path,
        sform_matrix: np.ndarray,
        description: str,
    ) -> None:
        """
        Write SFormMatrix into:
        1. NIfTI header
        2. JSON sidecar
        """

        img = nb.load(str(nii_path))
        data = img.get_fdata()
        header = img.header.copy()

        out_img = nb.Nifti1Image(data, sform_matrix, header)
        out_img.set_sform(sform_matrix, code=1)
        out_img.set_qform(sform_matrix, code=1)
        out_img.header.set_xyzt_units("micron")
        nb.save(out_img, str(nii_path))

        meta, json_path = bmeta.load_metadata(nii_path)

        meta["SFormMatrix"] = sform_matrix.tolist()
        meta["SFormMatrixAxis"] = ["X", "Y", "Z"]
        meta["SFormMatrixDescription"] = description

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)






class VolumeBuilder3D:
    def __init__(self, bids_root: str, original_thickness: float, volume_reorient: str="none"):
        self.bids_root = Path(bids_root).resolve()
        self.original_thickness = original_thickness
        self.volume_reorient = volume_reorient
        self.preproc_root = self.bids_root / "derivatives" / "2D-preproc"
        self.stacking_root = self.bids_root / "derivatives" / "3D-stacking"

        if not self.preproc_root.exists():
            raise FileNotFoundError(f"REPOSITORY NOT FOUND : {self.preproc_root}")

        self.stacking_root.mkdir(parents=True, exist_ok=True)

    def build_volume_output_path(self, subject_dir: Path, channel: str) -> Path:
        output_dir = self.stacking_root / subject_dir.name / "micr"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{subject_dir.name}_{channel}_desc-stacking_volume.nii.gz"
    
    def update_output_json(self, output_nii_path: Path, new_affine: np.ndarray, volume_shape: tuple[int, int, int]) -> None:
        """
        Update JSON sidecar for 3D volume with stacking metadata
        """

        meta, output_json = bmeta.load_metadata(output_nii_path)
        meta["VolumeReorientationMode"] = self.volume_reorient
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
    @staticmethod
    def map_old_index_to_reoriented_index(
        old_index: tuple[float, float, float],
        old_shape: tuple[int, int, int],
        mode: str,
    ) -> tuple[float, float, float]:
        """
        Convert an index from original volume space to reoriented volume space.

        old_index = (x, y, z)
        old_shape = (width, height, nb_slices)

        Example:
            mode = "x,-z,-y"

            old_index = (x, y, z)

            new_x = x
            new_y = nb_slices - 1 - z
            new_z = height - 1 - y
        """

        x, y, z = old_index

        if mode is None:
            return x, y, z

        mode = mode.strip().lower()

        if mode in ("", "none", "no", "identity", "x,y,z"):
            return x, y, z

        axes_map = {
            "x": 0,
            "y": 1,
            "z": 2,
        }

        # Same syntax as fslswapdim, example: "x,-z,-y"
        if "," in mode:
            old_values = [x, y, z]
            old_shape_values = list(old_shape)

            parts = [p.strip() for p in mode.split(",")]

            if len(parts) != 3:
                raise ValueError(
                    f"Invalid volume reorientation mode: {mode}. "
                    "Expected format like 'x,y,z' or 'x,-z,-y'."
                )

            new_index = []

            for part in parts:
                if part.startswith("-"):
                    axis_name = part[1:]
                    flip = True
                else:
                    axis_name = part
                    flip = False

                if axis_name not in axes_map:
                    raise ValueError(
                        f"Invalid axis '{part}' in volume reorientation mode: {mode}"
                    )

                old_axis = axes_map[axis_name]
                value = old_values[old_axis]

                if flip:
                    value = old_shape_values[old_axis] - 1 - value

                new_index.append(value)

            return tuple(new_index)

        # Operation syntax, example: "swap_yz+flip_y+flip_z"
        current_index = [x, y, z]
        current_shape = list(old_shape)

        operations = [op.strip() for op in mode.split("+") if op.strip()]

        for op in operations:
            if op == "flip_x":
                current_index[0] = current_shape[0] - 1 - current_index[0]

            elif op == "flip_y":
                current_index[1] = current_shape[1] - 1 - current_index[1]

            elif op == "flip_z":
                current_index[2] = current_shape[2] - 1 - current_index[2]

            elif op == "swap_xy":
                current_index = [current_index[1], current_index[0], current_index[2]]
                current_shape = [current_shape[1], current_shape[0], current_shape[2]]

            elif op == "swap_xz":
                current_index = [current_index[2], current_index[1], current_index[0]]
                current_shape = [current_shape[2], current_shape[1], current_shape[0]]

            elif op == "swap_yz":
                current_index = [current_index[0], current_index[2], current_index[1]]
                current_shape = [current_shape[0], current_shape[2], current_shape[1]]

            else:
                raise ValueError(
                    f"Invalid volume reorientation operation: {op}. "
                    "Allowed operations are: flip_x, flip_y, flip_z, "
                    "swap_xy, swap_xz, swap_yz."
                )

        return tuple(current_index)
    def reorient_volume_3d(self,volume: np.ndarray,resolution: list[float],mode: str) -> tuple[np.ndarray, list[float]]:
        """
        Reorient a 3D volume.

        Two syntaxes are supported.

        1) fslswapdim-like syntax:
            "x,y,z"       -> no change
            "x,-z,-y"     -> new X = old X, new Y = old Z reversed, new Z = old Y reversed
            "-x,y,z"      -> flip old X
            "z,y,x"       -> swap X and Z

        2) operation syntax:
            "none"                      -> no change
            "flip_x"                    -> reverse X axis
            "flip_y"                    -> reverse Y axis
            "flip_z"                    -> reverse Z axis
            "swap_xy"                   -> exchange X and Y
            "swap_xz"                   -> exchange X and Z
            "swap_yz"                   -> exchange Y and Z
            "swap_yz+flip_y+flip_z"     -> equivalent to "x,-z,-y"

        Important:
            volume is modified in voxel space using np.transpose and np.flip.
            resolution is reordered to stay consistent with the new axes.
        """

        if mode is None:
            return volume, resolution

        mode = mode.strip().lower()

        if mode in ("", "none", "no", "identity", "x,y,z"):
            return volume, resolution

        resolution = list(resolution)

        axes_map = {
            "x": 0,
            "y": 1,
            "z": 2,
        }

       
        if "," in mode:
            parts = [p.strip() for p in mode.split(",")]

            if len(parts) != 3:
                raise ValueError(
                    f"Invalid volume reorientation mode: {mode}. "
                    "Expected format like 'x,y,z' or 'x,-z,-y'."
                )

            transpose_axes = [] # will contain [0, 2, 1] => "x,-z,-y"
            flip_axes = [] # will contain the flipped axes (means we put - ) which is in our exemple z ,y => [1, 2]

            for new_axis, part in enumerate(parts):
                if not part:
                    raise ValueError(
                        f"Invalid empty axis in volume reorientation mode: {mode}"
                    )

                if part.startswith("-"):
                    axis_name = part[1:]
                    do_flip = True
                else:
                    axis_name = part
                    do_flip = False

                if axis_name not in axes_map:
                    raise ValueError(
                        f"Invalid axis '{part}' in volume reorientation mode: {mode}. "
                        "Allowed axes are x, y, z, -x, -y, -z."
                    )

                old_axis = axes_map[axis_name] # convert axes name to a number 
                transpose_axes.append(old_axis)

                if do_flip:
                    flip_axes.append(new_axis) # new_axis gives the index of the axe to flip from the loop "x,-z,-y" => [1, 2]
            # verify if we used each axe or not we avoid cases like this => "x,x,z" , [0, 0, 2] 
            if sorted(transpose_axes) != [0, 1, 2]: 
                raise ValueError(
                    f"Invalid volume reorientation mode: {mode}. "
                    "Each axis x, y, z must be used exactly once."
                )

            # Reorder axes
            volume = np.transpose(volume, transpose_axes)

            # Flip requested new axes
            for axis in flip_axes:
                volume = np.flip(volume, axis=axis)

            # Resolution follows the old axes for exemple : resolution = [res_x, res_y, res_z] 
            new_resolution = [resolution[old_axis] for old_axis in transpose_axes]

            return volume, new_resolution

       
        operations = [op.strip() for op in mode.split("+") if op.strip()]

        for op in operations:
            if op == "flip_x":
                volume = np.flip(volume, axis=0)

            elif op == "flip_y":
                volume = np.flip(volume, axis=1)

            elif op == "flip_z":
                volume = np.flip(volume, axis=2)

            elif op == "swap_xy":
                volume = np.transpose(volume, (1, 0, 2))
                resolution = [resolution[1], resolution[0], resolution[2]]

            elif op == "swap_xz":
                volume = np.transpose(volume, (2, 1, 0))
                resolution = [resolution[2], resolution[1], resolution[0]]

            elif op == "swap_yz":
                volume = np.transpose(volume, (0, 2, 1))
                resolution = [resolution[0], resolution[2], resolution[1]]

            else:
                raise ValueError(
                    f"Invalid volume reorientation operation: {op}. "
                    "Allowed operations are: flip_x, flip_y, flip_z, "
                    "swap_xy, swap_xz, swap_yz. "
                    "You can combine them with '+', for example: "
                    "'swap_yz+flip_y+flip_z'."
                )

        return volume, resolution
    @staticmethod
    def build_new_affine_matrix(volume_shape: tuple[int, int, int],resolution: list[float]) -> np.ndarray:
        """
        Build a simple NIfTI affine after volume reorientation.

        volume_shape:
            Shape of the final 3D volume, for example:
            (512, 80, 512)

        resolution:
            Voxel size for each final axis, for example:
            [0.05, 0.2, 0.05]

        The affine says:
            axis X has voxel size resolution[0]
            axis Y has voxel size resolution[1]
            axis Z has voxel size resolution[2]

        The origin is set so the volume is centered around (0, 0, 0).
        """

        volume_shape = np.array(volume_shape, dtype=float)
        resolution = np.array(resolution, dtype=float)

        if volume_shape.shape[0] != 3:
            raise ValueError(
                f"volume_shape must have 3 values, got {volume_shape}"
            )

        if resolution.shape[0] != 3:
            raise ValueError(
                f"resolution must have 3 values, got {resolution}"
            )

        affine = np.eye(4, dtype=float)

        # Voxel sizes on X, Y, Z
        affine[:3, :3] = np.diag(resolution)

        # Center the volume around 0,0,0
        affine[:3, 3] = -volume_shape * resolution / 2.0

        return affine
    
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
        
        # Métadonnées de référence (première slice du groupe)
        first_meta = sorted_slices[0][2]
        downsampling_factor = bmeta.get_downsampling_factor(first_meta)
        original_res = bmeta.get_original_resolution(first_meta)

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
            img = nb.load(str(nii_path))
            data = img.get_fdata()
            data_2d = np.squeeze(data)
            stack_of_slices[:, :, i] = data_2d

        stack_of_slices, new_resolution = self.reorient_volume_3d(stack_of_slices,new_resolution,self.volume_reorient)
        volume_shape = np.array(stack_of_slices.shape)

        new_affine = VolumeBuilder3D.build_new_affine_matrix(tuple(volume_shape),new_resolution)

        # Sauvegarder le volume
        out_img = nb.Nifti1Image(stack_of_slices, new_affine)
        out_img.header.set_xyzt_units("micron")
        output_path = self.build_volume_output_path(subject_dir, channel)
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

    parser = argparse.ArgumentParser(description="Slice preprocessing and 3D volume stacking")
    parser.add_argument("--bids_root", required=True, help="Path to BIDS root folder")
    parser.add_argument("--volume_reorient", required=False, default="none", help="3D volume reorientation: none, x,y,z, x,-z,-y, swap_yz+flip_y+flip_z, etc.")
    parser.add_argument("--padding_delta", required=False, type=int, default=100, help="Padding size in pixels")
    parser.add_argument("--original_thickness", required=False, type=float, default=200, help="Histological section thickness")
    args = parser.parse_args()

    proc = SlicePreprocessor(
        input_root=args.bids_root,
        output_root=args.bids_root,
        original_thickness=args.original_thickness,
        volume_reorient=args.volume_reorient,
    )

    downsampled_niftis = list(proc.downsampled_root.rglob("*.nii.gz"))
    preproc_niftis     = list(proc.preproc_root.rglob("*.nii.gz"))

    print(f"Downsampled: {len(downsampled_niftis)} files")
    print(f"Preproc:     {len(preproc_niftis)} files")

    if len(preproc_niftis) < len(downsampled_niftis):
        print("Preproc incomplete or missing — running SlicePreprocessor...")

        for subject_dir in bm.iter_subject_dirs(proc.downsampled_root):
            subject_niftis = list(bm.iter_subject_niftis(subject_dir))

            if not subject_niftis:
                continue

            target_shape = proc.compute_target_shape(subject_niftis, args.padding_delta, subject_dir.name)
            print(f"Subject: {subject_dir.name} — target shape: {target_shape}")

            sorted_subject_niftis = sorted(
                subject_niftis,
                key=lambda p: bmeta.get_z_index(bmeta.load_metadata(p)[0])
            )

            unique_slice_indices = sorted({
                int(bmeta.get_z_index(bmeta.load_metadata(p)[0]))
                for p in sorted_subject_niftis
                if bmeta.get_z_index(bmeta.load_metadata(p)[0]) is not None
            })

            slice_position_map = {
                slice_index: position
                for position, slice_index in enumerate(unique_slice_indices)
            }

            nb_slices = len(unique_slice_indices)

            first_meta, _ = bmeta.load_metadata(sorted_subject_niftis[0])
            downsampling_factor = bmeta.get_downsampling_factor(first_meta)
            original_res = bmeta.get_original_resolution(first_meta)
            downsampled_res = original_res * downsampling_factor

            old_shape = (
                int(target_shape[0]),
                int(target_shape[1]),
                int(nb_slices),
            )

            old_resolution = [
                downsampled_res,
                downsampled_res,
                args.original_thickness,
            ]

            tmp_volume = np.zeros(old_shape, dtype=np.uint8)

            tmp_builder = VolumeBuilder3D(
                bids_root=args.bids_root,
                original_thickness=args.original_thickness,
                volume_reorient=args.volume_reorient,
            )

            tmp_volume, new_resolution = tmp_builder.reorient_volume_3d(
                tmp_volume,
                old_resolution,
                args.volume_reorient,
            )

            volume_affine = VolumeBuilder3D.build_new_affine_matrix(
                tuple(tmp_volume.shape),
                new_resolution,
            )

            for nii_path in sorted_subject_niftis:
                meta, _ = bmeta.load_metadata(nii_path)
                slice_index = int(bmeta.get_z_index(meta))
                slice_position = slice_position_map[slice_index]
                output_path = proc.build_output_path(nii_path)

                if output_path.exists():
                    print(f"  SKIP (already exists): {nii_path.name}")
                    continue

                out = proc.process_one_slice(
                    nii_path=nii_path,
                    target_shape=target_shape,
                    subject_name=subject_dir.name,
                    volume_affine=volume_affine,
                    old_shape=old_shape,
                    slice_position=slice_position,
                )

                print(f"  IN : {nii_path.name}")
                print(f"  OUT: {out.name}")
    else:
        print("Preproc is complete — skipping SlicePreprocessor")

    print("\nRunning VolumeBuilder3D...")
    builder = VolumeBuilder3D(
        bids_root=args.bids_root,
        original_thickness=args.original_thickness,
        volume_reorient=args.volume_reorient
    )
    builder.build_all_volumes()

"""
python mimosa_stacking_2D_2_3D-2.py \
  --bids_root /envau/work/nit/users/boudlal.h/BIDS-una \
  --volume_reorient x,-z,-y \
  --original_thickness 200
"""