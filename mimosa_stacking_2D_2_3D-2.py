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
            return None 

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
    @classmethod
    def has_slice_index(cls, meta: dict) -> bool:
        return meta.get("SliceIndex") is not None





class SlicePreprocessor:
    def __init__(self, input_root: str, output_root: str, reorient_mode: str = "none"):
        self.input_root = Path(input_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.subject_max_sizes = {} # having track of max width and height for each subject 
        self.reorient_mode = reorient_mode

        self.downsampled_root = self.input_root / "derivatives" / "downsampled"
        self.preproc_root = self.output_root / "derivatives" / "preproc"

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
        meta, json_path=BidsTools.load_metadata(nii_path)
        width = meta.get("Width")
        height = meta.get("Height")

        if width is None or height is None:
            raise ValueError(f"Width/Height NOT FOUND IN {json_path}")

        return int(width), int(height)              
    
    def compute_target_shape(self, nii_paths, padding_delta, subject_name):
        max_width = 0
        max_height = 0

        # Check if rotation swaps dimensions
        swaps_dimensions = any(m in self.reorient_mode.split("+") 
                            for m in ["rot90_cw", "rot90_ccw"])

        for nii_path in nii_paths:
            width, height = self.get_slice_size_from_json(nii_path)

            # If rotation swaps axes, swap width and height
            if swaps_dimensions:
                width, height = height, width

            if width > max_width:
                max_width = width
            if height > max_height:
                max_height = height

        self.subject_max_sizes[subject_name] = (max_width, max_height)

        return max_width + padding_delta, max_height + padding_delta
    
    def reorient_slice_2d(self, data_2d: np.ndarray) -> np.ndarray:
        """
        Apply multiple 2D reorientation before padding
        """
        modes = self.reorient_mode.split("+")

        for mode in modes:
            mode = mode.strip()
            if mode == "none":
                pass
            elif mode == "flip_ud":
                data_2d = np.flipud(data_2d)
            elif mode == "flip_lr":
                data_2d = np.fliplr(data_2d)
            elif mode == "rot180":
                data_2d = np.rot90(data_2d, 2)
            elif mode == "rot90_cw":
                data_2d = np.rot90(data_2d, 3)
            elif mode == "rot90_ccw":
                data_2d = np.rot90(data_2d, 1)
            else:
                raise ValueError(f"UNKNOWN ROTATION MODE : {mode}")

        return data_2d
        
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
                f"Target shape {target_shape} smaller than the image {data_2d.shape} for {nii_path.name}"
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

        #  Lire les métadonnées de toutes les slices et trier selon Z
        sorted_slices = []
        skipped_slices = []

        for nii_path in nii_paths:
            meta, _ = BidsTools.load_metadata(nii_path)
            z_index = BidsTools.get_z_index(meta)

            if z_index is None:
                skipped_slices.append(nii_path.name)
                continue

            sorted_slices.append((z_index, nii_path, meta))
        sorted_slices.sort(key=lambda x: x[0])
        
        # Métadonnées de référence (première slice du groupe)
        first_meta = sorted_slices[0][2]
        downsampling_factor = BidsTools.get_downsampling_factor(first_meta)
        original_res = BidsTools.get_original_resolution(first_meta)

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

        new_affine = np.zeros((4, 4))
        new_affine[:3, :3] = np.diag(new_resolution)
        new_affine[:3, 3] = volume_shape * new_resolution / 2.0 * -1
        new_affine[3, 3] = 1.0

        # float32 instead of default float64 to reduce memory usage by half
        # (4 bytes vs 8 bytes per pixel) — float32 precision is sufficient for microscopy images
        # which have pixel values between 0 and 65535
        stack_of_slices = np.zeros((width, height, nb_slices), dtype=np.float32) 
        for i, (z_index, nii_path, meta) in enumerate(sorted_slices):
            img = nb.load(str(nii_path))
            data = img.get_fdata()
            data_2d = np.squeeze(data)
            stack_of_slices[:, :, i] = data_2d

        # Sauvegarder le volume
        out_img = nb.Nifti1Image(stack_of_slices, new_affine)
        output_path = self.build_volume_output_path(subject_dir, channel)
        nb.save(out_img, str(output_path))
        output_json = BidsTools.get_json_path(output_path)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump({}, f)
        self.update_output_json(output_path, new_affine, tuple(volume_shape))
        return output_path
    
    def build_all_volumes(self):
        for subject_dir in BidsTools.iter_subject_dirs(self.preproc_root):
            groups = BidsTools.group_subject_niftis_by_channel(subject_dir)

            for channel, nii_paths in groups.items():
                out = self.build_one_volume(subject_dir, channel, nii_paths)
                print("VOLUME:", out)
    
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Slice preprocessing and 3D volume stacking")
    parser.add_argument("--bids_root",          required=True,                  help="Path to BIDS root folder")
    parser.add_argument("--reorient_mode",      required=False, default="none", help="Reorientation mode: none, flip_ud, flip_lr, rot180, rot90_cw(clockwise), rot90_ccw — chain with '+' e.g. 'flip_ud+rot90_cw'")
    parser.add_argument("--padding_delta",      required=False, type=int,   default=100,   help="Padding size in pixels (default: 100)")
    parser.add_argument("--original_thickness", required=False, type=float, default=200, help="Histological section thickness  default 200 ")
    args = parser.parse_args()

    proc = SlicePreprocessor(
        input_root=args.bids_root,
        output_root=args.bids_root,
        reorient_mode=args.reorient_mode
    )

    downsampled_niftis = list(proc.downsampled_root.rglob("*.nii.gz"))
    preproc_niftis     = list(proc.preproc_root.rglob("*.nii.gz"))

    print(f"Downsampled: {len(downsampled_niftis)} files")
    print(f"Preproc:     {len(preproc_niftis)} files")

    if len(preproc_niftis) < len(downsampled_niftis):
        print("Preproc incomplete or missing — running SlicePreprocessor...")

        for subject_dir in BidsTools.iter_subject_dirs(proc.downsampled_root):
            subject_niftis = list(BidsTools.iter_subject_niftis(subject_dir))

            if not subject_niftis:
                continue

            target_shape = proc.compute_target_shape(subject_niftis, args.padding_delta, subject_dir.name)
            print(f"Subject: {subject_dir.name} — target shape: {target_shape}")

            for nii_path in subject_niftis:
                # Skip slices already preprocessed
                output_path = proc.build_output_path(nii_path)
                if output_path.exists():
                    print(f"  SKIP (already exists): {nii_path.name}")
                    continue

                out = proc.process_one_slice(nii_path, target_shape, subject_dir.name)
                print(f"  IN : {nii_path.name}")
                print(f"  OUT: {out.name}")
    else:
        print("Preproc is complete — skipping SlicePreprocessor")

    print("\nRunning VolumeBuilder3D...")
    builder = VolumeBuilder3D(
        bids_root=args.bids_root,
        original_thickness=args.original_thickness
    )
    builder.build_all_volumes()