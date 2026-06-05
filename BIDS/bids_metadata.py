import os
import yaml
import json
import re
from pathlib import Path
import shutil
import numpy as np
import nibabel as nb

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

def create_derivatives_descriptions(
    bids_root: str,
    cfg: dict,
    pipeline_names: list[str] | None = None,
) -> None:

    derivs = cfg.get("derivatives", {})
    if not derivs:
        raise ValueError("Key 'derivatives' missing in YAML")

    if pipeline_names is None:
        pipelines_to_create = list(derivs.keys())
    else:
        pipelines_to_create = pipeline_names

    for pipeline in pipelines_to_create:
        base_pipeline = pipeline.split("_res-")[0]

        if base_pipeline not in derivs:
            raise ValueError(
                f"Derivative '{base_pipeline}' missing in YAML. "
                f"Needed to create '{pipeline}'."
            )

        info = derivs[base_pipeline]

        deriv_path = Path(bids_root) / "derivatives" / pipeline
        deriv_path.mkdir(parents=True, exist_ok=True)

        desc_path = deriv_path / "dataset_description.json"
        if desc_path.exists():
            continue

        desc = info.get("dataset_description", {})
        if not desc:
            raise ValueError(
                f"Key 'dataset_description' missing for derivative '{base_pipeline}' in YAML"
            )

        with open(desc_path, "w", encoding="utf-8") as f:
            json.dump(desc, f, indent=2, ensure_ascii=False)

        print(f"dataset_description.json created for derivative '{pipeline}'")


def write_subject_sessions_tsv(bids_root: str, subject: str, ses_rows: list[dict]) -> None:
   
    sub_dir = os.path.join(bids_root, f"sub-{subject}")
    os.makedirs(sub_dir, exist_ok=True)

    path = os.path.join(sub_dir, f"sub-{subject}_sessions.tsv")

    lines = ["session_id\tacq_time"]
    for r in ses_rows:
        lines.append(f"{r['session_id']}\t{r['acq_time']}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"sessions.tsv created: sub-{subject}/sessions.tsv")

def write_samples_tsv(bids_root: Path, samples_rows: list) -> None:
    path = Path(bids_root) / "samples.tsv"
    cols = ["sample_id", "participant_id", "sample_type", "derived_from", "source_filename"]
    lines = ["\t".join(cols)]
    for r in samples_rows:
        line = [str(r.get(c, "n/a")) for c in cols]
        lines.append("\t".join(line))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("samples.tsv created")

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
    """reads metadata.yml and adds files + slice indices for each subject/sample.
    Does not overwrite existing slices if already defined manually."""
    yaml_path = Path(yaml_path)
    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    for entry in cfg.get("samples", {}).get("entries", []):
        subject_path = Path(entry["path"])
        subject      = entry.get("subject", "Unknown")

        if not subject_path.exists():
            print(f"WARNING: {subject} path not found: {subject_path}")
            continue

        # If no samples defined, create a default one
        if not entry.get("samples"):
            entry["samples"] = [{"sample_id": "sample-Cx", "files": []}]

        for sample in entry.get("samples", []):
            sample_id = sample["sample_id"]
            existing_files = sample.get("files", [])
            files = []

            for filename in sorted(subject_path.rglob("*.czi")):
                file_entry = {"filename": filename.name}

                # Keep existing slices if already defined — don't overwrite manual slices !
                existing_slices = next(
                    (f.get("slices") for f in existing_files
                     if f["filename"] == filename.name and f.get("slices")),
                    None
                )

                if existing_slices:
                    file_entry["slices"] = existing_slices  # ← keep manual slices
                else:
                    slices = extract_slices_from_filename(filename.name)
                    if slices:
                        file_entry["slices"] = slices

                files.append(file_entry)

            sample["files"] = files
            print(f"{subject} / {sample_id} → {len(files)} files added")

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

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

 
def map_index_after_reorientation(
    index: tuple[float, float, float],
    shape: tuple[float, float, float],
    reorient: str,
) -> tuple[float, float, float]:
    """
    Map a voxel index from the original stacked volume to the reoriented volume.

    This follows the same logic as:
        np.transpose(volume, transpose_axes)
        np.flip(volume, axis=flip_axes)

    This function is needed because a flip depends on the volume shape:
        new_index = shape - 1 - old_index
    """
    if is_identity_reorientation(reorient):
        return index

    transpose_axes, flip_axes = parse_reorientation_mode(reorient)

    old_values = list(index)
    old_shape = list(shape)

    new_index = []

    for new_axis, old_axis in enumerate(transpose_axes):
        value = old_values[old_axis]

        if new_axis in flip_axes:
            value = old_shape[old_axis] - 1.0 - value

        new_index.append(value)

    return tuple(new_index)


def build_centered_slice_sform(
    width: float,
    height: float,
    pixel_size: list[float],
    slice_position: int,
    nb_slices: int,
    thickness: float,
    reorient: str = "none",
    volume_width: float = None,
    volume_height: float = None,
) -> list[list[float]]:
    """
    Build a 2D slice SForm in the same centered reference as the final 3D volume.

    This does NOT use microscope/chunk/stage coordinates.

    The 2D slice is considered as a plane inside the original stacked volume:
        voxel (i, j, 0) of the 2D image corresponds to
        voxel (i, j, slice_position) in the 3D stack.

    If reorient is applied, we map these voxel indices using the same logic
    as the 3D stacking: transpose + flip.

    volume_width and volume_height must be the maximum size across ALL slices
    of this subject (before padding), so that the final_affine is identical
    for every slice and all slices share the same physical Z reference.

    If volume_width / volume_height are not provided, falls back to width / height
    (correct only if all slices have the same size).
    """
    width = float(width)
    height = float(height)
    nb_slices = float(nb_slices)

    px = float(pixel_size[0])
    py = float(pixel_size[1])
    th = float(thickness)

    # Use volume-level dimensions for the common reference frame.
    # This ensures final_affine is identical for all slices of the subject.
    vw = float(volume_width) if volume_width is not None else width
    vh = float(volume_height) if volume_height is not None else height

    original_shape = (vw, vh, nb_slices)
    original_resolution = [px, py, th]

    # Shape and resolution of the final reoriented volume.
    if is_identity_reorientation(reorient):
        final_shape = original_shape
        final_resolution = original_resolution
    else:
        transpose_axes, _ = parse_reorientation_mode(reorient)
        final_shape = tuple(original_shape[old_axis] for old_axis in transpose_axes)
        final_resolution = [original_resolution[old_axis] for old_axis in transpose_axes]

    final_affine = np.array(
        build_centered_affine(
            shape=final_shape,
            resolution=final_resolution,
        ),
        dtype=float,
    )

    # 2D voxel origin in the original 3D stack.
    old_origin = (0.0, 0.0, float(slice_position))

    # One step in 2D X, one step in 2D Y, and one step through slices.
    old_x_step = (1.0, 0.0, float(slice_position))
    old_y_step = (0.0, 1.0, float(slice_position))
    old_z_step = (0.0, 0.0, float(slice_position) + 1.0)

    # Map these indices to the final reoriented volume indices.
    new_origin = map_index_after_reorientation(
        old_origin,
        original_shape,
        reorient,
    )
    new_x_step = map_index_after_reorientation(
        old_x_step,
        original_shape,
        reorient,
    )
    new_y_step = map_index_after_reorientation(
        old_y_step,
        original_shape,
        reorient,
    )
    new_z_step = map_index_after_reorientation(
        old_z_step,
        original_shape,
        reorient,
    )

    origin_phys = final_affine @ np.array([*new_origin, 1.0])
    x_phys      = final_affine @ np.array([*new_x_step, 1.0])
    y_phys      = final_affine @ np.array([*new_y_step, 1.0])
    z_phys      = final_affine @ np.array([*new_z_step, 1.0])

    sform = np.eye(4, dtype=float)
    sform[:3, 0] = x_phys[:3] - origin_phys[:3]
    sform[:3, 1] = y_phys[:3] - origin_phys[:3]
    sform[:3, 2] = z_phys[:3] - origin_phys[:3]
    sform[:3, 3] = origin_phys[:3]

    return sform.tolist()


def build_centered_affine(
    shape: tuple[float, float, float],
    resolution: list[float],
) -> list[list[float]]:
    """
    Build a centered affine for a 3D volume.

    The center voxel of the volume is centered around physical coordinate (0,0,0).
    NIfTI voxel index (0,0,0) corresponds to the center of the first voxel.
    """
    shape = np.array(shape, dtype=float)
    resolution = np.array(resolution, dtype=float)

    affine = np.eye(4, dtype=float)
    affine[:3, :3] = np.diag(resolution)
    affine[:3, 3] = -(shape - 1.0) * resolution / 2.0

    return affine.tolist()

def add_sform_to_json_metadata(
    meta: dict,
    slice_position_map: dict[int, int],
    original_thickness: float,
    reorient: str = "none",
    nb_slices: int = None,
    volume_width: float = None,
    volume_height: float = None,
) -> dict:
    """
    Add SFormMatrix to metadata using a centered common volume reference.

    We do NOT use ChunkTransformationMatrix for placement.

    For non-padded 2D-downsampled files:
        - if WidthPhysical/HeightPhysical exist, they are used as the true physical size
          of the scene, normally computed from the raw CZI scene size and raw pixel size.
        - otherwise, physical size is approximated from Width/Height and PixelSize.

    volume_width / volume_height: maximum scene size in pixels across ALL scenes of
    this subject (after axis_swap, in the same axis convention as Width/Height in the
    metadata). Must be passed so that all slices share the same final_affine reference.
    If not provided, falls back to the per-slice size (incorrect when slices differ in size).

    nb_slices: total number of slices in the global volume. If None, falls back to
               len(slice_position_map).
    """

    slice_index = meta.get("SliceIndex")
    if slice_index is None:
        return meta

    slice_index = int(slice_index)

    if slice_index not in slice_position_map:
        return meta

    slice_position = int(slice_position_map[slice_index])

    if nb_slices is None:
        nb_slices = int(len(slice_position_map))
    else:
        nb_slices = int(nb_slices)

    pixel_size = meta["PixelSize"]
    px = float(pixel_size[0])
    py = float(pixel_size[1])

    if meta.get("WidthPhysical") is not None and meta.get("HeightPhysical") is not None:
        width_physical  = float(meta["WidthPhysical"])
        height_physical = float(meta["HeightPhysical"])

        width  = width_physical  / px
        height = height_physical / py

    else:
        width  = float(meta["Width"])
        height = float(meta["Height"])

        width_physical  = width  * px
        height_physical = height * py

        meta["WidthPhysical"]  = width_physical
        meta["HeightPhysical"] = height_physical

    sform = build_centered_slice_sform(
        width=width,
        height=height,
        pixel_size=pixel_size,
        slice_position=slice_position,
        nb_slices=nb_slices,
        thickness=original_thickness,
        reorient=reorient,
        volume_width=volume_width,
        volume_height=volume_height,
    )

    meta["SlicePosition"]   = slice_position
    meta["NumberOfSlices"]  = nb_slices

    meta["SFormMatrix"]             = sform
    meta["SFormReorientationMode"]  = reorient
    meta["SFormMatrixAxis"]         = ["X", "Y", "Z"]
    meta["SFormMatrixDescription"]  = (
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
    out_img.header.set_xyzt_units("micron")
    nb.save(out_img, str(nii_path))

    meta, json_path = load_metadata(nii_path)

    meta["SFormMatrix"] = sform_matrix.tolist()
    meta["SFormMatrixAxis"] = ["X", "Y", "Z"]
    meta["SFormMatrixDescription"] = description

    if reorient is not None:
        meta["SFormVolumeReorientationMode"] = reorient

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4)