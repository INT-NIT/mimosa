import os
import shutil
import numpy as np
import subprocess as sp
import nibabel as nb
from pathlib import Path
import json 

class BidsTools:
    @classmethod
    def get_json_path(self, nii_path: Path) -> Path:
        return Path(os.path.splitext(str(nii_path))[0] + ".json")
    @classmethod
    def load_metadata(self, nii_path: Path) -> dict:
        json_path = self.get_json_path(nii_path)

        if not json_path.exists():
            raise FileNotFoundError(f"JSON NOT FOUND FOR {nii_path.name}: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f) , json_path
    @classmethod
    def iter_subject_dirs(self, root: Path):
        for subject_dir in sorted(root.glob("sub-*")):
            if subject_dir.is_dir():
                yield subject_dir
    @classmethod
    def iter_subject_niftis(cls, subject_dir: Path):
        for nii_path in subject_dir.rglob("*.nii.gz"):
            yield nii_path
    @classmethod
    def copy_json_sidecar(self, input_nii_path: Path, output_nii_path: Path) -> None:
        """
        Copy JSON sidecar from input NIfTI to output NIfTI
        """
        input_json = self.get_json_path(input_nii_path)
        output_json = self.get_json_path(output_nii_path)

        if input_json.exists():
            shutil.copyfile(input_json, output_json)
        else:
            print(f"WARNING : NO JSON for {input_nii_path.name}")
    @classmethod
    def get_channel_from_path(self, nii_path: Path) -> str:
        parts = nii_path.name.split("_")

        for part in parts:
            if part.startswith("stain-"):
                return part.replace("stain-", "")

        raise ValueError(f"CHANNEL NOT FOUND  {nii_path.name}")
    @classmethod
    def get_z_index(cls, meta: dict) -> int:
        z_value = meta.get("SliceIndex")

        if z_value is None:
            raise ValueError("Slice index not found in JSON")

        return int(z_value)
    @classmethod    
    def group_subject_niftis_by_channel(self, subject_dir: Path):
        groups = {}
        for nii_path in subject_dir.rglob("*.nii.gz"):
            channel = self.get_channel_from_path(nii_path)
            groups.setdefault(channel, []).append(nii_path)
        return groups
    @classmethod
    def get_downsampling_factor(self, meta: dict) -> float:
        value = meta.get("DownsamplingFactor")

        if value is None:
            raise ValueError("DownsamplingFactor not found in the JSON ")

        return float(value)
    @classmethod    
    def get_original_resolution(self, meta: dict) -> float:
        signature = meta.get("AcquisitionSignature")

        if not signature:
            raise ValueError("AcquisitionSignature not found in the JSON ")

        marker = "resolution-"
        if marker not in signature:
            raise ValueError(f"Not expected AcquisitionSignature format: {signature}")

        value_part = signature.split(marker)[1]
        first_res = value_part.split("x")[0]

        return float(first_res)
    





class SlicePreprocessor:
    def __init__(self, input_root: str, output_root: str, reorient_mode: str = "flip_ud"):
        self.input_root = Path(input_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.subject_max_sizes = {} # having track of max width and height for each subject 
        self.reorient_mode = reorient_mode

        self.downsampled_root = self.input_root / "derivatives" / "downsampled"
        self.preproc_root = self.output_root / "derivatives" / "preproc"

        if not self.downsampled_root.exists():
            raise FileNotFoundError(f"Dossier introuvable: {self.downsampled_root}")

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
        meta, json_path=BidsTools.load_metadata(nii_path)
        width = meta.get("Width")
        height = meta.get("Height")

        if width is None or height is None:
            raise ValueError(f"Width/Height NOT FOUND IN {json_path}")

        return int(width), int(height)              
    
    def compute_target_shape(self, nii_paths: list[Path], padding_delta: int , subject_name: str) -> tuple[int, int]:
        """
        Compute target 2D shape for a group of slices:
        max width + padding_delta, max height + padding_delta
        """
        max_width = 0
        max_height = 0

        for nii_path in nii_paths:
            width, height = self.get_slice_size_from_json(nii_path)

            if width > max_width:
                max_width = width
            if height > max_height:
                max_height = height

        self.subject_max_sizes[subject_name] = (max_width, max_height)

        target_width = max_width + padding_delta
        target_height = max_height + padding_delta

        return target_width, target_height
    
    def reorient_slice_2d(self, data_2d: np.ndarray) -> np.ndarray:
        """
        Apply 2D reorientation before padding
        """
        if self.reorient_mode == "none":
            return data_2d
        elif self.reorient_mode == "flip_ud":
            return np.flipud(data_2d)
        elif self.reorient_mode == "flip_lr":
            return np.fliplr(data_2d)
        elif self.reorient_mode == "rot180":
            return np.rot90(data_2d, 2)
        else:
            raise ValueError(f"UNKNOWN ROTATION MODE : {self.reorient_mode}")
        
    def update_output_json(self, output_nii_path: Path, target_shape: tuple[int, int], subject_name: str) -> None:
        """
        Update copied JSON sidecar with preprocessing metadata
        """
        meta, output_json = BidsTools.load_metadata(output_nii_path)

        meta["ReorientationMode"] = self.reorient_mode
        meta["PaddingTargetShape"] = [int(target_shape[0]), int(target_shape[1])]
        meta["SubjectMaxSize"] = [
            int(self.subject_max_sizes[subject_name][0]),
            int(self.subject_max_sizes[subject_name][1]),
        ]

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)

    def process_one_slice(self, nii_path: Path, target_shape: tuple[int, int], subject_name: str) -> Path:
        """
        Load one input NIfTI, reorient it, pad it to target_shape,
        save it to derivatives/preproc, and copy its JSON sidecar.
        """
        output_path = self.build_output_path(nii_path)

        img = nb.load(str(nii_path))
        data = img.get_fdata()
        affine = img.affine
        header = img.header.copy()
        # flip , rotation , padding works more efficienly with 2D so we squeeze 3D (X,Y,Z)=> Z=1 to just (X,Y)
        data_2d = np.squeeze(data)

        data_2d = self.reorient_slice_2d(data_2d)

        current_width = data_2d.shape[0]
        current_height = data_2d.shape[1]

        target_width, target_height = target_shape

        shift_x = target_width - current_width
        shift_y = target_height - current_height

        if shift_x < 0 or shift_y < 0:
            raise ValueError(
                f"Target shape {target_shape} plus petite que l'image {data_2d.shape} pour {nii_path.name}"
            )

        padded_data_2d = np.pad(
            data_2d,
            (
                (round(shift_x / 2), shift_x - round(shift_x / 2)),
                (round(shift_y / 2), shift_y - round(shift_y / 2)),
            ),
            mode="constant",
            constant_values=0,
        )

        padded_data = np.expand_dims(padded_data_2d, axis=2)

        out_img = nb.Nifti1Image(padded_data, affine, header)
        nb.save(out_img, str(output_path))

        BidsTools.copy_json_sidecar(nii_path, output_path)
        self.update_output_json(output_path, target_shape, subject_name)
        return output_path





class VolumeBuilder3D:
    def __init__(self, bids_root: str, original_thickness: float):
        self.bids_root = Path(bids_root).resolve()
        self.original_thickness = original_thickness

        self.preproc_root = self.bids_root / "derivatives" / "preproc"
        self.stacking_root = self.bids_root / "derivatives" / "stacking"

        if not self.preproc_root.exists():
            raise FileNotFoundError(f"REPOSITORY NOT FOUND : {self.preproc_root}")

        self.stacking_root.mkdir(parents=True, exist_ok=True)

    def build_volume_output_path(self, subject_dir: Path, channel: str) -> Path:
        output_dir = self.stacking_root / subject_dir.name / "micr"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / f"{subject_dir.name}_{channel}_volume.nii.gz"
    
    def update_output_json(self, output_nii_path: Path, new_affine: np.ndarray, volume_shape: tuple[int, int, int]) -> None:
        """
        Update JSON sidecar for 3D volume with stacking metadata
        """

        meta, output_json = BidsTools.load_metadata(output_nii_path)

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

    def build_one_volume(self, subject_dir: Path, channel: str, nii_paths: list[Path]) -> Path:
        if not nii_paths:
            raise ValueError(f"NO SLICE FOUND FOR  {subject_dir.name} {channel}")

        # 1) Lire les métadonnées de toutes les slices et trier selon Z
        sorted_slices = []
        for nii_path in nii_paths:
            meta, _ = BidsTools.load_metadata(nii_path)
            z_index = BidsTools.get_z_index(meta)   # adapte le nom du champ dans cette fonction
            sorted_slices.append((z_index, nii_path, meta))

        sorted_slices.sort(key=lambda x: x[0])

        # 2) Métadonnées de référence (première slice du groupe)
        first_meta = sorted_slices[0][2]
        downsampling_factor = BidsTools.get_downsampling_factor(first_meta)
        original_res = BidsTools.get_original_resolution(first_meta)

        downsampled_res = original_res * downsampling_factor

        # 3) Lire la taille des slices déjà paddées/réorientées
        first_img = nb.load(str(sorted_slices[0][1]))
        first_data = np.squeeze(first_img.get_fdata())

        width = first_data.shape[0]
        height = first_data.shape[1]
        nb_slices = len(sorted_slices)

        volume_shape = np.array((width, height, nb_slices))

        # 4) Construire la résolution et l’affine du volume final
        new_resolution = [downsampled_res, downsampled_res, self.original_thickness]

        new_affine = np.zeros((4, 4))
        new_affine[:3, :3] = np.diag(new_resolution)
        new_affine[:3, 3] = volume_shape * new_resolution / 2.0 * -1
        new_affine[3, 3] = 1.0

        # 5) Empiler les slices dans l’ordre du Z
        stack_of_slices = np.zeros((width, height, nb_slices))

        for i, (z_index, nii_path, meta) in enumerate(sorted_slices):
            img = nb.load(str(nii_path))
            data = img.get_fdata()
            data_2d = np.squeeze(data)
            stack_of_slices[:, :, i] = data_2d

        # 6) Sauvegarder le volume
        out_img = nb.Nifti1Image(stack_of_slices, new_affine)
        output_path = self.build_volume_output_path(subject_dir, channel)
        nb.save(out_img, str(output_path))
        BidsTools.copy_json_sidecar(sorted_slices[0][1], output_path)
        self.update_output_json(output_path, new_affine, tuple(volume_shape))
        return output_path
    
    def build_all_volumes(self):
        for subject_dir in BidsTools.iter_subject_dirs(self.preproc_root):
            groups = BidsTools.group_subject_niftis_by_channel(subject_dir)

            for channel, nii_paths in groups.items():
                out = self.build_one_volume(subject_dir, channel, nii_paths)
                print("VOLUME:", out)
    
if __name__ == "__main__":
    proc = SlicePreprocessor(
        input_root="/envau/work/nit/users/boudlal.h/BIDS-2-sujets/",
        output_root="/envau/work/nit/users/boudlal.h/BIDS-2-sujets/"
    )

    padding_delta = 100

    for subject_dir in BidsTools.iter_subject_dirs(proc.downsampled_root):
        subject_niftis = list(BidsTools.iter_subject_niftis(subject_dir))

        if not subject_niftis:
            continue

        target_shape = proc.compute_target_shape(subject_niftis, padding_delta,subject_dir.name)

        print("SUBJECT :", subject_dir.name)
        print("TARGET SHAPE :", target_shape)

        for nii_path in subject_niftis:
            out = proc.process_one_slice(nii_path, target_shape,subject_dir.name)
            print("IN :", nii_path)
            print("OUT:", out)
    builder = VolumeBuilder3D(
    bids_root="/envau/work/nit/users/boudlal.h/BIDS-2-sujets/",
    original_thickness=0.100
    )

    builder.build_all_volumes()

