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

     

def build_centered_slice_sform(
    width: float,
    height: float,
    pixel_size: list[float],
    slice_position: int,
    nb_slices: int,
    thickness: float,
    reorient: str = "none",
) -> list[list[float]]:
    """
    Build a 2D slice SForm in a common centered volume reference.

    This function does NOT use microscope/chunk/stage coordinates.

    The center of the slice is placed at:
        X = 0
        Y = 0
        Z = centered slice position

    This makes the center stable across:
        - resolutions
        - padded / non-padded versions
        - final 3D stacking

    Important:
    sform[:3, 3] is the physical position of voxel (0,0,0),
    not the image center.
    """

    px = float(pixel_size[0]) * UM_TO_MM
    py = float(pixel_size[1]) * UM_TO_MM
    th = float(thickness) * UM_TO_MM

    width = float(width)
    height = float(height)

    # Position of the slice center in the common 3D volume reference.
    # Using (nb_slices - 1) / 2 keeps the middle slice centered around 0.
    center_z = (float(slice_position) - (float(nb_slices) - 1.0) / 2.0) * th

    # Voxel directions before reorientation.
    col_x = np.array([px, 0.0, 0.0], dtype=float)
    col_y = np.array([0.0, py, 0.0], dtype=float)
    col_z = np.array([0.0, 0.0, th], dtype=float)

    # Translation = physical position of voxel (0,0,0).
    # We place the image center at (0,0,center_z).
    origin = np.array(
        [
            -width * px / 2.0,
            -height * py / 2.0,
            center_z,
        ],
        dtype=float,
    )

    # Apply reorientation as a physical axis transform.
    # No shape - 1 here, because we are not mapping voxel indices.
    # We are transforming physical vectors.
    if not is_identity_reorientation(reorient):
        transpose_axes, flip_axes = parse_reorientation_mode(reorient)

        def reorient_vec(v: np.ndarray) -> np.ndarray:
            v_new = np.array(
                [v[transpose_axes[i]] for i in range(3)],
                dtype=float,
            )
            for ax in flip_axes:
                v_new[ax] *= -1.0
            return v_new

        col_x = reorient_vec(col_x)
        col_y = reorient_vec(col_y)
        col_z = reorient_vec(col_z)
        origin = reorient_vec(origin)

    sform = np.eye(4, dtype=float)
    sform[:3, 0] = col_x
    sform[:3, 1] = col_y
    sform[:3, 2] = col_z
    sform[:3, 3] = origin

    return sform.tolist()

def build_centered_affine(
    shape: tuple[float, float, float],
    resolution: list[float],
) -> list[list[float]]:
    """
    Build a centered affine for a 2D slice or a 3D volume.

    The image/volume is centered around physical coordinate (0,0,0).
    """
    shape = np.array(shape, dtype=float)
    resolution = np.array(resolution, dtype=float) *UM_TO_MM

    affine = np.eye(4, dtype=float)
    affine[:3, :3] = np.diag(resolution)
    affine[:3, 3] = -(shape - 1.0) * resolution / 2.0
    return affine.tolist()

def add_sform_to_json_metadata(
    meta: dict,
    slice_position_map: dict[int, int],
    original_thickness: float,
    reorient: str = "none",
) -> dict:
    """
    Add SFormMatrix to metadata using a centered common volume reference.

    We do NOT use ChunkTransformationMatrix for placement.

    For non-padded 2D-downsampled files:
        - if WidthPhysical/HeightPhysical exist, they are used as the true physical size
          of the scene, normally computed from the raw CZI scene size and raw pixel size.
        - otherwise, physical size is approximated from Width/Height and PixelSize.

    The SForm origin corresponds to voxel (0,0,0), not to the image center.
    The image center is placed at X=0, Y=0, and Z according to SlicePosition.
    """

    slice_index = meta.get("SliceIndex")
    if slice_index is None:
        return meta

    slice_index = int(slice_index)

    if slice_index not in slice_position_map:
        return meta

    slice_position = int(slice_position_map[slice_index])
    nb_slices = int(len(slice_position_map))

    pixel_size = meta["PixelSize"]
    px = float(pixel_size[0])
    py = float(pixel_size[1])

    # Preferred case:
    # WidthPhysical and HeightPhysical should come from the raw CZI scene:
    # raw_scene_width_pixels  * raw_pixel_size_um
    # raw_scene_height_pixels * raw_pixel_size_um
    if meta.get("WidthPhysical") is not None and meta.get("HeightPhysical") is not None:
        width_physical = float(meta["WidthPhysical"])
        height_physical = float(meta["HeightPhysical"])

        # build_centered_slice_sform expects width/height in pixels,
        # so we convert physical size back to "virtual pixels" at the current resolution.
        width = width_physical / px
        height = height_physical / py

    else:
        # Fallback:
        # use the current exported image size in pixels.
        width = float(meta["Width"])
        height = float(meta["Height"])

        width_physical = width * px
        height_physical = height * py

        meta["WidthPhysical"] = width_physical
        meta["HeightPhysical"] = height_physical

    sform = build_centered_slice_sform(
        width=width,
        height=height,
        pixel_size=pixel_size,
        slice_position=slice_position,
        nb_slices=nb_slices,
        thickness=original_thickness,
        reorient=reorient,
    )

    meta["SlicePosition"] = slice_position
    meta["NumberOfSlices"] = nb_slices

    meta["SFormMatrix"] = sform
    meta["SFormReorientationMode"] = reorient
    meta["SFormMatrixAxis"] = ["X", "Y", "Z"]
    meta["SFormMatrixDescription"] = (
        "SForm matrix placing this 2D slice in a centered common volume reference. "
        "Chunk/stage coordinates are not used. "
        "For non-padded slices, the physical field of view is based on "
        "WidthPhysical/HeightPhysical when available. "
        f"Slice center is resolution-invariant with reorient={reorient}."
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