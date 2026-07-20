import numpy as np
import nibabel as nb
from pathlib import Path
import json 
from BIDS import bids_metadata as bmeta
from BIDS import bids_manager as bm

class SlicePreprocessor:
    def __init__(self,input_root: str,output_root: str,original_thickness: float,  res_label: str,reorient: str = "none",):     
        self.input_root = Path(input_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.original_thickness = original_thickness
        self.res_label = res_label
        self.reorient = reorient
        self.subject_max_sizes = {} # having track of max width and height for each subject 
        self.downsampled_root = self.input_root / "derivatives" / "2D" / "downsampled" 
        self.preproc_root     = self.output_root / "derivatives" / "2D" / "padded" 
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

        # Both reduction methods are accepted: desc-downsampled (decimation)
        # and desc-downsampledavg (block mean). The longer one is tested first,
        # otherwise "_desc-downsampled" would never match "downsampledavg".
        if "_desc-downsampledavg_" in name:
            name = name.replace("_desc-downsampledavg_", "_desc-padded_")
        elif "_desc-downsampled_" in name:
            name = name.replace("_desc-downsampled_", "_desc-padded_")
        elif "_FLUO.nii.gz" in name:
            name = name.replace("_FLUO.nii.gz", "_desc-padded_FLUO.nii.gz")

        output_path = self.preproc_root / relative_path.parent / name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    def get_slice_size_from_nifti(self, nii_path: Path) -> tuple[int, int]:
        img = nb.load(str(nii_path))
        data_2d = np.squeeze(img.get_fdata())
        return int(data_2d.shape[0]), int(data_2d.shape[1])
    
    def compute_target_shape(self, nii_paths, padding_delta, subject_name):
        max_width = 0
        max_height = 0

        for nii_path in nii_paths:
            width, height = self.get_slice_size_from_nifti(nii_path)

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
                reorient=self.reorient,
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

        The preproc file gets a final SFormMatrix in the common centered
        volume reference. It does not use microscope/chunk coordinates.

        Important:
        - non-padded and padded images do not have the same SForm translation
        - but their image center is placed at the same physical center
        - the padded image SForm is the one compatible with the final 3D volume
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
                f"Target shape {target_shape} smaller than the image "
                f"{data_2d.shape} for {nii_path.name}"
            )

        pad_x_before = round(shift_x / 2)
        pad_y_before = round(shift_y / 2)
        pad_x_after = shift_x - pad_x_before
        pad_y_after = shift_y - pad_y_before
        padded_data_2d = np.pad(
            data_2d,
            (
                (pad_x_before, pad_x_after),
                (pad_y_before, pad_y_after),
            ),
            mode="constant",
            constant_values=0,
        )
        padded_data = np.expand_dims(padded_data_2d, axis=2)

        meta, _ = bmeta.load_metadata(nii_path)

        slice_position = int(meta["SlicePosition"])
        nb_slices = int(meta["NumberOfSlices"])

        nonpadded_sform = np.array(meta["SFormMatrix"], dtype=float)

        preproc_sform = nonpadded_sform.copy()
        preproc_sform[:3, 3] = (
            nonpadded_sform[:3, 3]
            - pad_x_before * nonpadded_sform[:3, 0]
            - pad_y_before * nonpadded_sform[:3, 1]
        )

        out_img = nb.Nifti1Image(padded_data, preproc_sform, header)
        out_img.set_sform(preproc_sform, code=1)
        out_img.set_qform(preproc_sform, code=1)
        out_img.header.set_xyzt_units("mm")
        nb.save(out_img, str(output_path))

        bmeta.copy_json_sidecar(nii_path, output_path)
        self.update_output_json(output_path, target_shape, subject_name)

        self.write_sform_to_nifti_and_json(
            nii_path=output_path,
            sform_matrix=preproc_sform,
            description=(
                "SForm matrix for padded 2D-preproc slice in centered common "
                f"volume reference, without chunk/stage coordinates, "
                f"using reorient={self.reorient}."
            ),
        )

        return output_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="2D slice preprocessing")
    parser.add_argument("-bids_root", required=True, help="Path to BIDS root folder")
    parser.add_argument("-padding_delta", required=False, type=int, default=100, help="Padding size in pixels")
    parser.add_argument("-original_thickness", required=False, type=float, default=200, help="Histological section thickness")
    parser.add_argument("-res",required=True,help="Resolution label to preprocess, for example 4x")
    parser.add_argument("-reorient",required=False,default="none",help="Reference reorientation used to compute SFormMatrix for preprocessed 2D slices")
    args = parser.parse_args()

    proc = SlicePreprocessor(
        input_root=args.bids_root,
        output_root=args.bids_root,
        original_thickness=args.original_thickness,
        res_label=args.res,
        reorient=args.reorient,
    )
    
    downsampled_niftis = [p for p in proc.downsampled_root.rglob("*.nii.gz") if f"_res-{args.res}_" in p.name]
    preproc_niftis     = [p for p in proc.preproc_root.rglob("*.nii.gz")     if f"_res-{args.res}_" in p.name]

    print(f"Downsampled: {len(downsampled_niftis)} files")
    print(f"Preproc:     {len(preproc_niftis)} files")

    if len(preproc_niftis) >= len(downsampled_niftis):
        print("Preproc is complete — skipping SlicePreprocessor")
    else:
        print("Preproc incomplete or missing — running SlicePreprocessor...")

        for subject_dir in bm.iter_subject_dirs(proc.downsampled_root):
            subject_niftis = [
                p for p in bm.iter_subject_niftis(subject_dir)
                if f"_res-{args.res}_" in p.name
            ]
            if not subject_niftis:
                continue

            target_shape = proc.compute_target_shape(
                subject_niftis,
                args.padding_delta,
                subject_dir.name,
            )
            sorted_subject_niftis = sorted(
                subject_niftis,
                key=lambda p: bmeta.get_z_index(bmeta.load_metadata(p)[0])
            )

            print(f"Subject: {subject_dir.name} — target shape: {target_shape}")

            for nii_path in sorted_subject_niftis:
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
  -bids_root /envau/work/nit/users/boudlal.h/BIDS-una \
  -res 4x \
  -padding_delta 100 \
  -original_thickness 100
"""
