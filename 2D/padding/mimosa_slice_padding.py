import os, sys
# Make the repo root (the folder that contains core/) importable, whatever the
# depth of this script, so "from core.bids import ..." works.
_ROOT = os.path.abspath(os.path.dirname(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.isdir(os.path.join(_ROOT, "core")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
from nibabel.processing import resample_from_to
import numpy as np
import nibabel as nb
from pathlib import Path
import json
from core.bids import bids_metadata as bmeta
from core.bids import bids_manager as bm

class SlicePreprocessor:
    def __init__(self, input_root: str, output_root: str, res_label: str, reorient: str = "none"):
        self.input_root = Path(input_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.res_label = res_label
        self.reorient = reorient
        self.subject_max_sizes = {} # having track of max width and height for each subject 
        self.subject_native_target = {}
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
        data_2d = np.squeeze(np.asarray(img.dataobj))
        return int(data_2d.shape[0]), int(data_2d.shape[1])
    
    def compute_target_shape(self, nii_paths, padding_delta, subject_name):

        max_native_width = 0
        max_native_height = 0

        max_ds_width = 0
        max_ds_height = 0

        factor = None

        for nii_path in nii_paths:

            # Taille réelle du NIfTI downsampled
            ds_width, ds_height = self.get_slice_size_from_nifti(nii_path)

            max_ds_width = max(max_ds_width, ds_width)
            max_ds_height = max(max_ds_height, ds_height)

            # Métadonnées natives
            meta, _ = bmeta.load_metadata(nii_path)

            native_width = int(meta["NativeWidthPixels"])
            native_height = int(meta["NativeHeightPixels"])

            current_factor = float(meta["DownsamplingFactor"])

            max_native_width = max(
                max_native_width,
                native_width,
            )

            max_native_height = max(
                max_native_height,
                native_height,
            )

            if factor is None:
                factor = current_factor

            elif not np.isclose(factor, current_factor):
                raise ValueError(
                    f"Different DownsamplingFactor values for {subject_name}: "
                    f"{factor} and {current_factor}"
                )


        if factor is None:
            raise ValueError(
                f"No slices found for {subject_name}"
            )


        # padding_delta reste exprimé en pixels DS.
        # On le convertit en pixels natifs.
        native_target_width = (
            max_native_width
            + padding_delta * factor
        )

        native_target_height = (
            max_native_height
            + padding_delta * factor
        )


        # IMPORTANT :
        # on mémorise le canvas NATIF commun
        self.subject_native_target[subject_name] = (
            native_target_width,
            native_target_height,
        )


        # Conversion du canvas natif vers la grille DS
        target_width = int(
            np.ceil(native_target_width / factor)
        )

        target_height = int(
            np.ceil(native_target_height / factor)
        )


        # Sécurité
        target_width = max(
            target_width,
            max_ds_width,
        )

        target_height = max(
            target_height,
            max_ds_height,
        )


        # Garder une taille impaire
        if target_width % 2 == 0:
            target_width += 1

        if target_height % 2 == 0:
            target_height += 1


        self.subject_max_sizes[subject_name] = (
            max_ds_width,
            max_ds_height,
        )


        print(
            f"{subject_name}: "
            f"max native=({max_native_width}, {max_native_height}), "
            f"factor={factor}, "
            f"native target=({native_target_width}, {native_target_height}), "
            f"DS target=({target_width}, {target_height})"
        )


        return target_width, target_height
    
        
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
        # One single convention: everything in float32.
        data = img.get_fdata().astype(np.float32)
        header = img.header.copy()

        data_2d = np.squeeze(data)

        current_width = data_2d.shape[0]
        current_height = data_2d.shape[1]

        target_width, target_height = target_shape

        if target_width < current_width or target_height < current_height:
            raise ValueError(
                f"Target shape {target_shape} smaller than the image "
                f"{data_2d.shape} for {nii_path.name}"
            )

        meta, _ = bmeta.load_metadata(nii_path)

        slice_position = int(meta["SlicePosition"])
        nb_slices = int(meta["NumberOfSlices"])

        nonpadded_sform = np.array(meta["SFormMatrix"], dtype=float)


        # ------------------------------------------------------------
        # 1. Informations de la grille native de CETTE coupe
        # ------------------------------------------------------------

        native_width = int(meta["NativeWidthPixels"])
        native_height = int(meta["NativeHeightPixels"])

        native_pixel_x = float(meta["NativePixelSize"][0]) / 1000.0
        native_pixel_y = float(meta["NativePixelSize"][1]) / 1000.0


        # ------------------------------------------------------------
        # 2. Taille native commune calculée dans compute_target_shape()
        # ------------------------------------------------------------

        native_target_width, native_target_height = (
            self.subject_native_target[subject_name]
        )


        # ------------------------------------------------------------
        # 3. Origine native actuelle de la coupe
        # ------------------------------------------------------------

        native_origin_x = (
            -(native_width - 1) / 2.0 * native_pixel_x
        )

        native_origin_y = (
            -(native_height - 1) / 2.0 * native_pixel_y
        )


        # ------------------------------------------------------------
        # 4. Origine du canvas NATIF commun
        # ------------------------------------------------------------

        target_origin_x = (
            -(native_target_width - 1) / 2.0 * native_pixel_x
        )

        target_origin_y = (
            -(native_target_height - 1) / 2.0 * native_pixel_y
        )


        # ------------------------------------------------------------
        # 5. Différence physique à corriger
        # ------------------------------------------------------------

        delta_x_mm = target_origin_x - native_origin_x
        delta_y_mm = target_origin_y - native_origin_y


        # Taille physique d'un pixel DS
        step_x_mm = np.linalg.norm(nonpadded_sform[:3, 0])
        step_y_mm = np.linalg.norm(nonpadded_sform[:3, 1])


        # Pour voir combien cela représente en pixels DS.
        # Ces valeurs peuvent être fractionnaires :
        # 0.125 pixel, 0.27 pixel, etc.
        shift_x_vox = delta_x_mm / step_x_mm
        shift_y_vox = delta_y_mm / step_y_mm

        print(
            f"  Native-grid correction: "
            f"dx={delta_x_mm:.6f} mm ({shift_x_vox:.4f} DS vox), "
            f"dy={delta_y_mm:.6f} mm ({shift_y_vox:.4f} DS vox)"
        )


        # ------------------------------------------------------------
        # 6. Construire la SForm commune du padded
        # ------------------------------------------------------------

        preproc_sform = nonpadded_sform.copy()

        preproc_sform[:3, 3] = (
            nonpadded_sform[:3, 3]
            + shift_x_vox * nonpadded_sform[:3, 0]
            + shift_y_vox * nonpadded_sform[:3, 1]
        )


        # ------------------------------------------------------------
        # 7. Resampling de l'image DS vers cette nouvelle grille
        # ------------------------------------------------------------

        source_data = np.expand_dims(
            data_2d.astype(np.float32),
            axis=2,
        )

        source_img = nb.Nifti1Image(
            source_data,
            nonpadded_sform,
        )

        source_img.set_sform(nonpadded_sform, code=1)
        source_img.set_qform(nonpadded_sform, code=1)


        target = (
            (target_width, target_height, 1),
            preproc_sform,
        )

        resampled_img = resample_from_to(
            source_img,
            target,
            order=1,
            mode="constant",
            cval=0.0,
        )

        padded_data = np.asarray(
            resampled_img.dataobj,
            dtype=np.float32,
        )

        padded_data = padded_data.astype(np.float32)
        header.set_data_dtype(np.float32)
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

    parser = argparse.ArgumentParser(description="2D slice padding")
    parser.add_argument("-bids_root", required=True, help="Path to BIDS root folder")
    parser.add_argument("-padding_delta", required=False, type=int, default=100, help="Padding size in pixels")
    parser.add_argument("-res",required=True,help="Resolution label to pad, for example 8x")
    parser.add_argument("-reorient",required=False,default="none",help="Reference reorientation used to compute SFormMatrix for preprocessed 2D slices")
    args = parser.parse_args()

    proc = SlicePreprocessor(
        input_root=args.bids_root,
        output_root=args.bids_root,
        res_label=args.res,
        reorient=args.reorient,
    )
    
    downsampled_niftis = [p for p in proc.downsampled_root.rglob("*.nii.gz") if f"_res-{args.res}_" in p.name]
    padded_niftis      = [p for p in proc.preproc_root.rglob("*.nii.gz")     if f"_res-{args.res}_" in p.name]

    print("=" * 60)
    print("MIMOSA - 2D slice padding")
    print(f"  BIDS root                : {args.bids_root}")
    print(f"  Resolution               : res-{args.res}")
    print(f"  Downsampled slices found : {len(downsampled_niftis)}")
    print(f"  Already padded           : {len(padded_niftis)}")
    print("=" * 60)

    if not downsampled_niftis:
        print(f"No downsampled slices found for res-{args.res} - nothing to pad.")
        print("Run the NIfTI conversion first with a -df matching this resolution "
              "(e.g. -df 8 produces res-8x).")
    elif len(padded_niftis) >= len(downsampled_niftis):
        print(f"All {len(downsampled_niftis)} slices are already padded - nothing to do.")
    else:
        remaining = len(downsampled_niftis) - len(padded_niftis)
        print(f"Padding {remaining} remaining slice(s)...\n")

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

