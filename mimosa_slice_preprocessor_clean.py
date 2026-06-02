import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import nibabel as nb
import numpy as np

from BIDS import bids_manager as bm
from BIDS import bids_metadata as bmeta


class SlicePreprocessor:
    """Pad 2D downsampled NIfTI slices and recompute their 2D SForm matrices."""

    def __init__(
        self,
        input_root: str,
        output_root: str,
        original_thickness: float,
        res_label: str,
        reorient: str = "none",
        debug: bool = True,
    ):
        self.input_root = Path(input_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.original_thickness = original_thickness
        self.res_label = res_label
        self.reorient = reorient
        self.debug = debug

        self.downsampled_root = self.input_root / "derivatives" / f"2D-downsampled_res-{self.res_label}"
        self.preproc_root = self.output_root / "derivatives" / f"2D-preproc_res-{self.res_label}"
        self.subject_max_sizes: Dict[str, Tuple[int, int]] = {}

        if not self.downsampled_root.exists():
            raise FileNotFoundError(f"Repository not found: {self.downsampled_root}")

        self.preproc_root.mkdir(parents=True, exist_ok=True)

    def log(self, *args) -> None:
        if self.debug:
            print(*args)

    def build_output_path(self, nii_path: Path) -> Path:
        """Mirror the downsampled hierarchy into 2D-preproc and rename desc."""
        relative_path = nii_path.relative_to(self.downsampled_root)
        name = relative_path.name

        if "_desc-downsampled_" in name:
            name = name.replace("_desc-downsampled_", "_desc-preproc_")
        elif "_FLUO.nii.gz" in name:
            name = name.replace("_FLUO.nii.gz", "_desc-preproc_FLUO.nii.gz")

        output_path = self.preproc_root / relative_path.parent / name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    @staticmethod
    def get_slice_index(nii_path: Path) -> int:
        meta, _ = bmeta.load_metadata(nii_path)
        z_index = bmeta.get_z_index(meta)
        if z_index is None:
            raise ValueError(f"SliceIndex not found for {nii_path}")
        return int(z_index)

    @staticmethod
    def get_2d_shape(nii_path: Path) -> Tuple[int, int]:
        """Use the real NIfTI data shape, not rounded JSON Width/Height."""
        data = np.squeeze(nb.load(str(nii_path)).dataobj)
        if data.ndim != 2:
            raise ValueError(f"Expected a 2D slice after squeeze, got shape {data.shape} for {nii_path.name}")
        return int(data.shape[0]), int(data.shape[1])

    def compute_target_shape(self, nii_paths: Iterable[Path], padding_delta: int, subject_name: str) -> Tuple[int, int]:
        max_width = 0
        max_height = 0

        for nii_path in nii_paths:
            width, height = self.get_2d_shape(nii_path)
            max_width = max(max_width, width)
            max_height = max(max_height, height)

        self.subject_max_sizes[subject_name] = (max_width, max_height)
        return max_width + padding_delta, max_height + padding_delta

    @staticmethod
    def build_slice_position_map(nii_paths: Iterable[Path]) -> Dict[int, int]:
        """Map each anatomical SliceIndex to its compact Z position in the 3D volume."""
        slice_indices = sorted({SlicePreprocessor.get_slice_index(p) for p in nii_paths})
        return {slice_index: position for position, slice_index in enumerate(slice_indices)}

    def warn_duplicate_slice_indices(self, nii_paths: Iterable[Path]) -> None:
        """Warn when the same SliceIndex appears with different PixelSize values."""
        seen: Dict[int, Tuple[Path, object]] = {}

        for nii_path in nii_paths:
            meta, _ = bmeta.load_metadata(nii_path)
            z_index = int(bmeta.get_z_index(meta))
            pixel_size = meta.get("PixelSize")
            pixel_key = tuple(float(x) for x in pixel_size[:2]) if pixel_size is not None else None

            if z_index in seen:
                old_path, old_pixel_key = seen[z_index]
                if old_pixel_key != pixel_key:
                    print(
                        "WARNING same SliceIndex with different PixelSize:",
                        f"SliceIndex={z_index}",
                        f"File1={old_path.name} PixelSize={old_pixel_key}",
                        f"File2={nii_path.name} PixelSize={pixel_key}",
                    )
            else:
                seen[z_index] = (nii_path, pixel_key)

    def update_output_json(self, output_nii_path: Path, target_shape: Tuple[int, int], subject_name: str) -> None:
        meta, output_json = bmeta.load_metadata(output_nii_path)

        meta["PaddingTargetShape"] = [int(target_shape[0]), int(target_shape[1])]
        meta["SubjectMaxSize"] = [
            int(self.subject_max_sizes[subject_name][0]),
            int(self.subject_max_sizes[subject_name][1]),
        ]
        meta["Preprocessing"] = {
            "Description": "2D slice padded to subject-level target shape and SForm recomputed",
            "ResolutionLabel": self.res_label,
            "OriginalThickness": float(self.original_thickness),
            "Reorient": self.reorient,
        }

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=4)

    def process_one_slice(
        self,
        nii_path: Path,
        target_shape: Tuple[int, int],
        subject_name: str,
        slice_position: int,
        nb_slices: int,
    ) -> Path:
        output_path = self.build_output_path(nii_path)

        img = nb.load(str(nii_path))
        data_2d = np.squeeze(img.get_fdata())
        header = img.header.copy()

        if data_2d.ndim != 2:
            raise ValueError(f"Expected 2D data, got shape {data_2d.shape} for {nii_path.name}")

        current_width, current_height = data_2d.shape
        target_width, target_height = target_shape

        shift_x = target_width - current_width
        shift_y = target_height - current_height
        if shift_x < 0 or shift_y < 0:
            raise ValueError(f"Target shape {target_shape} smaller than image {data_2d.shape} for {nii_path.name}")

        pad_x_before = shift_x // 2
        pad_y_before = shift_y // 2

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
        self.log(
            "DEBUG SHAPE",
            nii_path.name,
            "nii_shape=", data_2d.shape,
            "json Width/Height=", meta.get("Width"), meta.get("Height"),
            "target_shape=", target_shape,
        )

        preproc_sform = np.asarray(
            bmeta.build_2d_sform_for_volume(
                width=target_width,
                height=target_height,
                pixel_size=meta["PixelSize"],
                slice_position=slice_position,
                nb_slices=nb_slices,
                thickness=self.original_thickness,
                reorient=self.reorient,
                pad_delta=(0, 0),
            ),
            dtype=float,
        )

        out_img = nb.Nifti1Image(padded_data, preproc_sform, header)
        out_img.set_sform(preproc_sform, code=1)
        out_img.set_qform(preproc_sform, code=1)
        out_img.header.set_xyzt_units("micron")
        nb.save(out_img, str(output_path))

        bmeta.copy_json_sidecar(nii_path, output_path)
        self.update_output_json(output_path, target_shape, subject_name)
        bmeta.write_sform_to_nifti_and_json(
            nii_path=output_path,
            sform_matrix=preproc_sform,
            description=f"SForm matrix recomputed for padded 2D-preproc using reorient={self.reorient}",
            reorient=self.reorient,
        )

        return output_path

    def process_subject(self, subject_dir: Path, padding_delta: int, overwrite: bool = False) -> None:
        subject_niftis = sorted(list(bm.iter_subject_niftis(subject_dir)), key=self.get_slice_index)
        if not subject_niftis:
            return

        target_shape = self.compute_target_shape(subject_niftis, padding_delta, subject_dir.name)
        slice_position_map = self.build_slice_position_map(subject_niftis)
        nb_slices = len(slice_position_map)

        self.warn_duplicate_slice_indices(subject_niftis)
        print(f"Subject: {subject_dir.name} — target shape: {target_shape} — nb_slices: {nb_slices}")

        for nii_path in subject_niftis:
            output_path = self.build_output_path(nii_path)
            if output_path.exists() and not overwrite:
                print(f"  SKIP already exists: {nii_path.name}")
                continue

            slice_index = self.get_slice_index(nii_path)
            slice_position = slice_position_map[slice_index]

            self.log(
                "DEBUG PREPROC",
                nii_path.name,
                "SliceIndex=", slice_index,
                "slice_position=", slice_position,
                "nb_slices=", nb_slices,
            )

            out = self.process_one_slice(
                nii_path=nii_path,
                target_shape=target_shape,
                subject_name=subject_dir.name,
                slice_position=slice_position,
                nb_slices=nb_slices,
            )

            print(f"  IN : {nii_path.name}")
            print(f"  OUT: {out.name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="2D slice preprocessing")
    parser.add_argument("--bids_root", required=True, help="Path to BIDS root folder")
    parser.add_argument("--padding_delta", type=int, default=100, help="Padding size in pixels")
    parser.add_argument("--original_thickness", type=float, default=100, help="Histological section thickness in micrometers")
    parser.add_argument("--res", required=True, help="Resolution label to preprocess, for example 4x or 8x")
    parser.add_argument("--reorient", default="none", help="Reference reorientation used to compute SFormMatrix")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing preprocessed files")
    parser.add_argument("--no_debug", action="store_true", help="Reduce debug logs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    proc = SlicePreprocessor(
        input_root=args.bids_root,
        output_root=args.bids_root,
        original_thickness=args.original_thickness,
        res_label=args.res,
        reorient=args.reorient,
        debug=not args.no_debug,
    )

    print("Running SlicePreprocessor...")
    print("Downsampled root:", proc.downsampled_root)
    print("Preproc root:    ", proc.preproc_root)

    for subject_dir in bm.iter_subject_dirs(proc.downsampled_root):
        proc.process_subject(subject_dir, padding_delta=args.padding_delta, overwrite=args.overwrite)

    print("[SUCCESS] Preprocessing done.")


if __name__ == "__main__":
    main()
