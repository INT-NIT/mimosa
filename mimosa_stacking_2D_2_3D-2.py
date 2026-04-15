import os
import shutil
import numpy as np
import subprocess as sp
import nibabel as nb
from pathlib import Path


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
    def iter_input_niftis(self):
        """
       iteration over all niffti files in derivatives/downsampled 
        """
        for nii_path in self.downsampled_root.rglob("*.nii.gz"):
            yield nii_path # returns nii files one by one not all at same time

    def iter_subject_niftis(self, subject_dir: Path):
        """
        Iterate over all NIfTI files for one subject
        """
        for nii_path in subject_dir.rglob("*.nii.gz"):
            yield nii_path

    def iter_subject_dirs(self):
        """
        Iterate over subject directories inside derivatives/downsampled
        """
        for subject_dir in sorted(self.downsampled_root.glob("sub-*")):
            if subject_dir.is_dir():
                yield subject_dir
            
    def build_output_path(self, nii_path: Path) -> Path:
        """
        preserve same hierarchy of derivatives/downsampled  in derivatives/preproc 
        """
        relative_path = nii_path.relative_to(self.downsampled_root)
        output_path = self.preproc_root / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    def get_json_path(self, nii_path: Path) -> Path:
        """
        Return the sidecar JSON path corresponding to a .nii.gz file
        """
        return Path(os.path.splitext(str(nii_path))[0] + ".json")

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
    def get_slice_size_from_json(self, nii_path: Path) -> tuple[int, int]:
        """
            Read width and height of one slice from its JSON sidecar
        """
        json_path = self.get_json_path(nii_path)

        if not json_path.exists():
            raise FileNotFoundError(f"JSON introuvable pour {nii_path.name}: {json_path}")

        import json
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

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
            raise ValueError(f"UNKNOWN Reorientation mode : {self.reorient_mode}")
        
    def process_one_slice(self, nii_path: Path ,  target_shape: tuple[int, int]) -> Path:
        """
        For now:
        - load input NIfTI
        - save it to derivatives/preproc with same hierarchy
        - copy JSON sidecar
        """
        output_path = self.build_output_path(nii_path)

        img = nb.load(str(nii_path))
        data = img.get_fdata() # intensités des pixels 
        affine = img.affine
        header = img.header.copy()

        out_img = nb.Nifti1Image(data, affine, header)
        nb.save(out_img, str(output_path))

        self.copy_json_sidecar(nii_path, output_path)

        return output_path



if __name__ == "__main__":
    proc = SlicePreprocessor(
        input_root="/envau/work/nit/users/boudlal.h/BIDS-2-sujets/",
        output_root="/envau/work/nit/users/boudlal.h/BIDS-2-sujets/"
    )

    padding_delta = 100

    for subject_dir in proc.iter_subject_dirs():
        subject_niftis = list(proc.iter_subject_niftis(subject_dir))

        if not subject_niftis:
            continue

        target_shape = proc.compute_target_shape(subject_niftis, padding_delta,subject_dir.name)

        print("SUBJECT :", subject_dir.name)
        print("TARGET SHAPE :", target_shape)

        for nii_path in subject_niftis:
            out = proc.process_one_slice(nii_path, target_shape)
            print("IN :", nii_path)
            print("OUT:", out)
    























