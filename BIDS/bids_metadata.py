import os
import yaml
import json
import re
from pathlib import Path
import shutil
import numpy as np
import nibabel as nb

UM_TO_MM=1.0/1000
def load_metadata_config(config_path: Path) -> dict:
    with open(Path(config_path), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_metadata(nii_path: Path) -> tuple:
    json_path = get_json_path(nii_path)
    if not json_path.exists():
        raise FileNotFoundError(f"JSON NOT FOUND FOR {nii_path.name}: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f), json_path

def create_dataset_description(bids_root: Path, cfg: dict) -> None:
    path = Path(bids_root) / "dataset_description.json"
    if path.exists():
        return
    desc = cfg.get("dataset_description", {})
    if not desc:
        raise ValueError("Key dataset_description missing in YAML")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(desc, f, indent=2, ensure_ascii=False)
    print("dataset_description.json created")

def create_participants_files(bids_root: Path, cfg: dict) -> None:
    bids_root = Path(bids_root)

    # participants.json
    json_path = bids_root / "participants.json"
    if not json_path.exists():
        participants_json = cfg.get("participants_json", {})
        if not participants_json:
            raise ValueError("Key participants_json missing in YAML")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(participants_json, f, indent=2, ensure_ascii=False)
        print("participants.json created")

    # participants.tsv
    tsv_path = bids_root / "participants.tsv"
    if tsv_path.exists():
        return
    participants_tsv = cfg.get("participants_tsv", {})
    if not participants_tsv:
        raise ValueError("Key participants_tsv missing in YAML")
    cols = participants_tsv.get("columns", ["participant_id"])
    rows = participants_tsv.get("rows", [])
    lines = ["\t".join(cols)]
    for r in rows:
        line = [str(r.get(c, "n/a")) for c in cols]
        lines.append("\t".join(line))
    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("participants.tsv created")

def create_derivatives_descriptions(bids_root: str, cfg: dict) -> None:
    derivs = cfg.get("derivatives", {})
    if not derivs:
        raise ValueError("Key 'derivatives' missing in YAML")

    # Créer seulement 2D ici — 3D sera créé par le script stacking
    for folder in ["2D"]:
        deriv_path = Path(bids_root) / "derivatives" / folder
        deriv_path.mkdir(parents=True, exist_ok=True)

        desc_path = deriv_path / "dataset_description.json"
        if desc_path.exists():
            continue

        info = derivs.get(folder, {})
        desc = info.get("dataset_description", {})
        if not desc:
            print(f"WARNING: no dataset_description for '{folder}' in YAML, skipping")
            continue

        with open(desc_path, "w", encoding="utf-8") as f:
            json.dump(desc, f, indent=2, ensure_ascii=False)

        print(f"dataset_description.json created for derivative '{folder}'")
        
def write_subject_sessions_tsv(bids_root: str, subject: str, ses_rows: list[dict]) -> None:
    sub_dir = os.path.join(bids_root, f"sub-{subject}")
    os.makedirs(sub_dir, exist_ok=True)

    path = os.path.join(sub_dir, f"sub-{subject}_sessions.tsv")

    lines = ["session_id\tacq_time"]
    for r in ses_rows:
        # Tronquer à YYYY-MM-DDTHH:MM:SS
        acq_time = str(r["acq_time"])
        acq_time = acq_time.split(".")[0]  # ← supprime les microsecondes et timezone
        lines.append(f"{r['session_id']}\t{acq_time}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def write_samples_tsv(bids_root: Path, samples_rows: list) -> None:
    path = Path(bids_root) / "samples.tsv"

    cols = [
        "sample_id",
        "participant_id",
        "sample_type",
        "anatomical_region",
        "source_filename",
    ]

    lines = ["\t".join(cols)]

    for r in samples_rows:
        line = [
            str(r.get("sample_id", "n/a")),
            str(r.get("participant_id", "n/a")),
            str(r.get("sample_type", "n/a")),
            str(r.get("anatomical_region", "n/a")),
            str(r.get("source_filename", "n/a")),
        ]
        lines.append("\t".join(line))

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    json_path = Path(bids_root) / "samples.json"
    samples_json = {
        "sample_type": {
            "Description": "Type of sample from ENCODE Biosample Type."
        },
        "anatomical_region": {
            "Description": "Anatomical region associated with the sample, for example midbrain, cerebellum, brainstem, cerebrum."
        },
        "source_filename": {
            "Description": "Original source CZI filename."
        },
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(samples_json, f, indent=2, ensure_ascii=False)

    print("samples.tsv created")
    print("samples.json created")

def write_micr_sidecar_json(image_path: Path, meta: dict) -> None:
    """writes the sidecar JSON file for a given image"""
    json_path = get_json_path(Path(image_path))
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"sidecar created: {json_path.name}")

def copy_json_sidecar(input_nii_path: Path, output_nii_path: Path) -> None:
    """Copy JSON sidecar from input NIfTI to output NIfTI"""
    input_json  = get_json_path(Path(input_nii_path))
    output_json = get_json_path(Path(output_nii_path))
    if input_json.exists():
        shutil.copyfile(input_json, output_json)
    else:
        print(f"WARNING : NO JSON for {Path(input_nii_path).name}")

def get_json_path(image_path: Path) -> Path:
    """
    Returns the JSON sidecar path for NIfTI or TIFF images.

    Examples:
        image.nii.gz -> image.json
        image.nii    -> image.json
        image.tif    -> image.json
        image.tiff   -> image.json
    """
    image_path = Path(image_path)
    name = image_path.name

    if name.endswith(".nii.gz"):
        json_name = name[:-7] + ".json"
    elif name.endswith(".tif"):
        json_name = name[:-4] + ".json"


    return image_path.parent / json_name
def extract_slices_from_filename(filename: str) -> list[int]:
    """ex: MTO10092101_Cx_008-056.czi -> [8, 56]"""
    match = re.search(r'_(\d+(?:[-_]\d+)+)\.czi$', filename)
    if match:
        return [int(n) for n in re.split(r'[-_]', match.group(1))]
    return []

def get_slices_for_file(cfg: dict, filename: str) -> list:
    """Returns list of slice numbers for a given CZI filename from YAML"""
    for entry in cfg.get("samples", {}).get("entries", []):
        for sample in entry.get("samples", []):
            for f in sample.get("files", []):
                if f["filename"] == filename:
                    return f.get("slices", [])
    return []

def get_z_index(meta: dict) -> int:
    """Returns SliceIndex from JSON metadata"""
    z_value = meta.get("SliceIndex")
    if z_value is None:
        return None
    return int(z_value)

def get_downsampling_factor(meta: dict) -> float:
    """Returns DownsamplingFactor from JSON metadata"""
    value = meta.get("DownsamplingFactor")
    if value is None:
        raise ValueError("DownsamplingFactor not found in the JSON")
    return float(value)

def get_original_resolution(meta: dict) -> float:
    """Returns original resolution from AcquisitionSignature in JSON metadata"""
    signature = meta.get("AcquisitionSignature")
    if not signature:
        raise ValueError("AcquisitionSignature not found in the JSON")
    marker = "resolution-"
    if marker not in signature:
        raise ValueError(f"Not expected AcquisitionSignature format: {signature}")
    value_part = signature.split(marker)[1]
    first_res = value_part.split("x")[0]
    return float(first_res)

def has_slice_index(meta: dict) -> bool:
    """Returns True if SliceIndex is present in JSON metadata"""
    return meta.get("SliceIndex") is not None

def update_yaml_with_slices(yaml_path: Path) -> dict:
    """
    Read metadata.yml and add CZI files + slice indices for each sample/region.

    Expected YAML structure:

    samples:
      entries:
        - path: /path/to/czi/folder
          subject: Una
          samples:
            - sample_type: technical sample
              derived_from: midbrain
              participant_id: sub-Una
              files:

    Behavior:
    - If files is empty/null, scan the subject path and add all .czi files.
    - If files already contains filenames, keep only those files.
    - For each file, fill slices from the filename when possible.
    - Existing manual slices are preserved.
    """
    yaml_path = Path(yaml_path)

    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    for entry in cfg.get("samples", {}).get("entries", []):
        subject_path = Path(entry["path"])
        subject = entry.get("subject", "Unknown")

        if not subject_path.exists():
            print(f"WARNING: {subject} path not found: {subject_path}")
            continue

        if not entry.get("samples"):
            entry["samples"] = [
                {
                    "participant_id": f"sub-{subject}",
                    "sample_type": "technical sample",
                    "derived_from": "n/a",
                    "files": [],
                }
            ]

        for sample in entry.get("samples", []):
            region = sample.get("derived_from", "n/a")
            existing_files = sample.get("files") or []

            updated_files = []

            if existing_files:
                # Keep only files already listed in this sample/region.
                for f in existing_files:
                    filename = f.get("filename")
                    if not filename:
                        continue

                    file_entry = {"filename": filename}

                    if f.get("slices"):
                        file_entry["slices"] = f["slices"]
                    else:
                        slices = extract_slices_from_filename(filename)
                        if slices:
                            file_entry["slices"] = slices

                    updated_files.append(file_entry)

                print(
                    f"{subject} / {region} → "
                    f"{len(updated_files)} files kept from YAML"
                )

            else:
                # files: null or files: [] => scan all .czi files in the subject path.
                for czi_path in sorted(subject_path.rglob("*.czi")):
                    file_entry = {"filename": czi_path.name}

                    slices = extract_slices_from_filename(czi_path.name)
                    if slices:
                        file_entry["slices"] = slices

                    updated_files.append(file_entry)

                print(
                    f"{subject} / {region} → "
                    f"{len(updated_files)} files added by scan"
                )

            sample["files"] = updated_files

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(
            cfg,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    return cfg

def get_slice_position_map_from_config(cfg: dict) -> dict[int, int]:
    """
    Build a map SliceIndex -> position in the global stack.

    Example:
        SliceIndex 2   -> 0
        SliceIndex 4   -> 1
        SliceIndex 452 -> N
    """
    slice_indices = []

    for entry in cfg.get("samples", {}).get("entries", []):
        for sample in entry.get("samples", []):
            for file_entry in sample.get("files", []):
                for s in file_entry.get("slices", []):
                    try:
                        slice_indices.append(int(s))
                    except Exception:
                        continue

    unique_slices = sorted(set(slice_indices))

    return {
        slice_index: position
        for position, slice_index in enumerate(unique_slices)
    }

def is_identity_reorientation(mode: str) -> bool:
    if mode is None:
        return True

    mode = mode.strip().lower()
    return mode in ("", "none", "no", "identity", "x,y,z")


def parse_reorientation_mode(mode: str) -> tuple[list[int], list[int]]:
        """
        Parse reorient mode once.

        Returns:
            transpose_axes: old axes order used to create new volume
            flip_axes: new axes to flip after transpose

        Example:
            "x,-z,-y"
            transpose_axes = [0, 2, 1]
            flip_axes = [1, 2]
        """
        if is_identity_reorientation(mode):
            return [0, 1, 2], []

        mode = mode.strip().lower()

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

            transpose_axes = []
            flip_axes = []

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

                old_axis = axes_map[axis_name]
                transpose_axes.append(old_axis)

                if do_flip:
                    flip_axes.append(new_axis)

            if sorted(transpose_axes) != [0, 1, 2]:
                raise ValueError(
                    f"Invalid volume reorientation mode: {mode}. "
                    "Each axis x, y, z must be used exactly once."
                )

            return transpose_axes, flip_axes

        transpose_axes = [0, 1, 2]
        flip_axes = []

        operations = [op.strip() for op in mode.split("+") if op.strip()]

        for op in operations:
            if op == "flip_x":
                flip_axes.append(0)

            elif op == "flip_y":
                flip_axes.append(1)

            elif op == "flip_z":
                flip_axes.append(2)

            elif op == "swap_xy":
                transpose_axes = [
                    transpose_axes[1],
                    transpose_axes[0],
                    transpose_axes[2],
                ]

                flip_axes = [
                    1 if axis == 0 else
                    0 if axis == 1 else
                    axis
                    for axis in flip_axes
                ]

            elif op == "swap_xz":
                transpose_axes = [
                    transpose_axes[2],
                    transpose_axes[1],
                    transpose_axes[0],
                ]

                flip_axes = [
                    2 if axis == 0 else
                    0 if axis == 2 else
                    axis
                    for axis in flip_axes
                ]

            elif op == "swap_yz":
                transpose_axes = [
                    transpose_axes[0],
                    transpose_axes[2],
                    transpose_axes[1],
                ]

                flip_axes = [
                    2 if axis == 1 else
                    1 if axis == 2 else
                    axis
                    for axis in flip_axes
                ]

            else:
                raise ValueError(
                    f"Invalid volume reorientation operation: {op}. "
                    "Allowed operations are: flip_x, flip_y, flip_z, "
                    "swap_xy, swap_xz, swap_yz."
                )

        return transpose_axes, flip_axes

def build_slice_sform(
    pixel_size: list[float],
    native_pixel_size: list[float],
    native_width: int,
    native_height: int,
    slice_position: int,
    nb_slices: int,
    thickness: float,
) -> list[list[float]]:
    """
    Build the SForm of one exported 2D NIfTI slice.

    All resolutions produced from the same native CZI scene use:
    - the same physical origin;
    - their own exported pixel resolution;
    - the same Z position.

    This function does not modify or interpolate image values.
    """

    if native_width <= 0 or native_height <= 0:
        raise ValueError(
            "native_width and native_height must be positive"
        )

    if nb_slices <= 0:
        raise ValueError("nb_slices must be positive")

    if not 0 <= slice_position < nb_slices:
        raise ValueError(
            f"Invalid slice position {slice_position} "
            f"for {nb_slices} slices"
        )

    # Resolution of the exported image, such as res-4x or res-8x.
    resolution_x_mm = float(pixel_size[0]) * UM_TO_MM
    resolution_y_mm = float(pixel_size[1]) * UM_TO_MM

    # Native CZI resolution.
    native_resolution_x_mm = (
        float(native_pixel_size[0]) * UM_TO_MM
    )
    native_resolution_y_mm = (
        float(native_pixel_size[1]) * UM_TO_MM
    )

    spacing_z_mm = float(thickness) * UM_TO_MM

    # Common X/Y origin calculated from the native CZI grid.
    # Therefore res-4x and res-8x from the same scene start
    # at exactly the same physical position.
    origin_x_mm = -(
        (float(native_width) - 1.0)
        * native_resolution_x_mm
    ) / 2.0

    origin_y_mm = -(
        (float(native_height) - 1.0)
        * native_resolution_y_mm
    ) / 2.0

    # Physical Z position of this slice.
    origin_z_mm = (
        float(slice_position)
        - (float(nb_slices) - 1.0) / 2.0
    ) * spacing_z_mm

    sform = np.array(
        [
            [
                resolution_x_mm,
                0.0,
                0.0,
                origin_x_mm,
            ],
            [
                0.0,
                resolution_y_mm,
                0.0,
                origin_y_mm,
            ],
            [
                0.0,
                0.0,
                spacing_z_mm,
                origin_z_mm,
            ],
            [
                0.0,
                0.0,
                0.0,
                1.0,
            ],
        ],
        dtype=np.float64,
    )

    return sform.tolist()

def build_centered_affine(
    shape: tuple[float, float, float],
    resolution: list[float],
    reorient: str = "none",
) -> list[list[float]]:
    """
    Build a centered affine for a 3D volume, encoding axis flips.

    For flipped axes: diagonal is negative, origin is positive.
    This ensures physical center = (0,0,0) regardless of flips,
    and matches the convention used in build_centered_slice_sform.
    """
    shape_arr      = np.array(shape,      dtype=float)
    resolution_mm  = np.array(resolution, dtype=float) * UM_TO_MM

    affine = np.eye(4, dtype=float)
    affine[:3, :3] = np.diag(resolution_mm)
    affine[:3, 3]  = -((shape_arr - 1.0) * resolution_mm) / 2.0

    if not is_identity_reorientation(reorient):
        _, flip_axes = parse_reorientation_mode(reorient)
        for ax in flip_axes:
            affine[ax, ax] *= -1.0          
            affine[ax, 3]  = -affine[ax, 3] 

    return affine.tolist()
def add_sform_to_json_metadata(
    meta: dict,
    slice_position_map: dict[int, int],
    original_thickness: float,
) -> dict:
    """
    Add the SForm of an exported 2D NIfTI slice to its metadata.

    The SForm is calculated from:
    - the actual exported image dimensions;
    - the exported pixel resolution;
    - the position of the slice in the global stack;
    - the physical spacing between slices.

    No interpolation or image resampling is performed.
    """

    slice_index = meta.get("SliceIndex")

    if slice_index is None:
        return meta

    slice_index = int(slice_index)

    if slice_index not in slice_position_map:
        raise ValueError(
            f"SliceIndex {slice_index} is not present "
            "in slice_position_map"
        )

    slice_position = int(slice_position_map[slice_index])
    nb_slices = int(len(slice_position_map))

   

    pixel_size = meta.get("PixelSize")

    if pixel_size is None or len(pixel_size) < 2:
        raise ValueError(
            f"Missing or invalid PixelSize for SliceIndex={slice_index}"
        )
    native_pixel_size = meta.get("NativePixelSize")
    native_width = meta.get("NativeWidthPixels")
    native_height = meta.get("NativeHeightPixels")

    if native_pixel_size is None or len(native_pixel_size) < 2:
        raise ValueError(
            f"Missing NativePixelSize for SliceIndex={slice_index}"
        )

    if native_width is None or native_height is None:
        raise ValueError(
            f"Missing native dimensions for SliceIndex={slice_index}. "
            "Expected NativeWidthPixels and NativeHeightPixels."
        )

    sform = build_slice_sform(
        pixel_size=pixel_size,
        native_pixel_size=native_pixel_size,
        native_width=int(native_width),
        native_height=int(native_height),
        slice_position=slice_position,
        nb_slices=nb_slices,
        thickness=original_thickness,
    )

    meta["SlicePosition"] = slice_position
    meta["NumberOfSlices"] = nb_slices
    meta["SFormMatrix"] = sform
    meta["SFormMatrixUnits"] = "mm"
    meta["SFormReorientationMode"] = "none"
    meta["SFormMatrixAxis"] = ["X", "Y", "Z"]

    meta["SFormMatrixDescription"] = (
    "SForm matrix placing the exported NIfTI slice in a common "
    "physical reference. The X and Y origins are calculated from "
    "the native CZI dimensions and native pixel size, so all "
    "resolutions produced from the same scene share the same origin. "
    "The SForm spacing uses the exported PixelSize. "
    "The Z position is calculated from SlicePosition, "
    "NumberOfSlices and the histological slice spacing. "
    "No additional interpolation or resampling is performed "
    "when creating this matrix."
)
    return meta
def write_sform_to_nifti_and_json(
    nii_path,
    sform_matrix,
    description: str,
    reorient: str = None,
) -> None:


    img = nb.load(str(nii_path))
    data = img.get_fdata()
    header = img.header.copy()

    sform_matrix = np.array(sform_matrix, dtype=float)

    out_img = nb.Nifti1Image(data, sform_matrix, header)
    out_img.set_sform(sform_matrix, code=1)
    out_img.set_qform(sform_matrix, code=1)
    out_img.header.set_xyzt_units("mm")
    nb.save(out_img, str(nii_path))

    meta, json_path = load_metadata(nii_path)
    meta["SFormMatrix"] = sform_matrix.tolist()
    meta["SFormMatrixUnits"] = "mm"

    meta["SFormMatrixAxis"] = ["X", "Y", "Z"]
    meta["SFormMatrixDescription"] = description

    if reorient is not None:
        meta["SFormVolumeReorientationMode"] = reorient

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4)