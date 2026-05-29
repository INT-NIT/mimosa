import numpy as np
import nibabel as nb
from pathlib import Path
import json 
from BIDS import bids_metadata as bmeta
from BIDS import bids_manager as bm

class SlicePreprocessor:
    def __init__(
        self,input_root: str,output_root: str,original_thickness: float,  res_label: str,):     
        self.input_root = Path(input_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.original_thickness = original_thickness
        self.res_label = res_label
        self.subject_max_sizes = {} # having track of max width and height for each subject 
        self.downsampled_root = self.input_root / "derivatives" / f"2D-downsampled_res-{self.res_label}"
        self.preproc_root = self.output_root / "derivatives" / f"2D-preproc_res-{self.res_label}"
        if not self.downsampled_root.exists():
            raise FileNotFoundError(f"Repository not found : {self.downsampled_root}")

        self.preproc_root.mkdir(parents=True, exist_ok=True)

    def build_output_path(self, nii_path: Path) -> Path:
        """
        preserve same hierarchy of derivatives/downsampled in derivatives/preproc
        and rename desc-downsampled to desc-preproc
        """
        relative_path = nii_path.relative_to(self.downsampled_root)
        name = relative_path.name

        if "_desc-downsampled_" in name:
            name = name.replace("_desc-downsampled_", "_desc-preproc_")
        elif "_FLUO.nii.gz" in name:
            name = name.replace("_FLUO.nii.gz", "_desc-preproc_FLUO.nii.gz")

        output_path = self.preproc_root / relative_path.parent / name
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

    def write_sform_to_nifti_and_json(
            self,
            nii_path: Path,
            sform_matrix: np.ndarray,
            description: str,
        ) -> None:
            bmeta.write_sform_to_nifti_and_json(
                nii_path=nii_path,
                sform_matrix=sform_matrix,
                description=description,
            )   

    def process_one_slice(
        self,
        nii_path: Path,
        target_shape: tuple[int, int],
        subject_name: str,
    ) -> Path:
        """
        Load one input NIfTI, pad it to target_shape,
        save it to derivatives/2D-preproc, and copy its JSON sidecar.

        The downsampled file already has its SFormMatrix from the HPC converter.
        For the preproc file, we adapt this SFormMatrix to account for padding.
        """
        output_path = self.build_output_path(nii_path)

        img = nb.load(str(nii_path))
        data = img.get_fdata()
        header = img.header.copy()

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

        meta, _ = bmeta.load_metadata(nii_path)

        if "SFormMatrix" in meta:
            downsampled_sform = np.array(meta["SFormMatrix"], dtype=float)
        else:
            downsampled_sform = img.affine

        preproc_sform = downsampled_sform.copy()

        # The preproc image has padding before the real image.
        # Its pixel (pad_x_before, pad_y_before) corresponds to the old downsampled pixel (0,0).
        # Therefore the new pixel (0,0) is shifted backward in physical space.
        preproc_sform[:3, 3] = (
            downsampled_sform[:3, 3]
            - pad_x_before * downsampled_sform[:3, 0]
            - pad_y_before * downsampled_sform[:3, 1]
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
            description="SForm matrix copied from 2D-downsampled and adjusted for preprocessing padding",
        )

        return output_path




if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="2D slice preprocessing")
    parser.add_argument("--bids_root", required=True, help="Path to BIDS root folder")
    parser.add_argument("--padding_delta", required=False, type=int, default=100, help="Padding size in pixels")
    parser.add_argument("--original_thickness", required=False, type=float, default=200, help="Histological section thickness")
    parser.add_argument("--res",required=True,help="Resolution label to preprocess, for example 4x")
    args = parser.parse_args()

    proc = SlicePreprocessor(
        input_root=args.bids_root,
        output_root=args.bids_root,
        original_thickness=args.original_thickness,
        res_label=args.res
    )

    downsampled_niftis = list(proc.downsampled_root.rglob("*.nii.gz"))
    preproc_niftis = list(proc.preproc_root.rglob("*.nii.gz"))

    print(f"Downsampled: {len(downsampled_niftis)} files")
    print(f"Preproc:     {len(preproc_niftis)} files")

    if len(preproc_niftis) >= len(downsampled_niftis):
        print("Preproc is complete — skipping SlicePreprocessor")
    else:
        print("Preproc incomplete or missing — running SlicePreprocessor...")

        for subject_dir in bm.iter_subject_dirs(proc.downsampled_root):
            subject_niftis = list(bm.iter_subject_niftis(subject_dir))

            if not subject_niftis:
                continue

            target_shape = proc.compute_target_shape(
                subject_niftis,
                args.padding_delta,
                subject_dir.name,
            )

            print(f"Subject: {subject_dir.name} — target shape: {target_shape}")

            for nii_path in subject_niftis:
                output_path = proc.build_output_path(nii_path)

                if output_path.exists():
                    print(f"  SKIP (already exists): {nii_path.name}")
                    continue

                out = proc.process_one_slice(
                    nii_path=nii_path,
                    target_shape=target_shape,
                    subject_name=subject_dir.name,
                )

                print(f"  IN : {nii_path.name}")
                print(f"  OUT: {out.name}")
"""
python mimosa_slice_preprocessor.py \
  --bids_root /envau/work/nit/users/boudlal.h/BIDS-una \
  --res 4x \
  --padding_delta 100 \
  --original_thickness 200
"""
