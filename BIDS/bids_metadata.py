import os
import yaml
import json  
import re
from pathlib import Path
import shutil


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
    for pipeline, info in derivs.items():
        deriv_path = Path(bids_root) / "derivatives" / pipeline
        deriv_path.mkdir(parents=True, exist_ok=True)
        desc_path = deriv_path / "dataset_description.json"
        if desc_path.exists():
            continue
        desc = info.get("dataset_description", {})
        if not desc:
            raise ValueError(f"Key 'dataset_description' missing for derivative '{pipeline}' in YAML")
        with open(desc_path, "w", encoding="utf-8") as f:
            json.dump(desc, f, indent=2, ensure_ascii=False)
        print(f"dataset_description.json created for derivative '{pipeline}'")

def create_micr_json(micr_folder: str, manufacturer: str, illumination: str, cfg: dict) -> None:
    """Creates micr.json from YAML manual fields + auto fields from CZI reader"""
    path = os.path.join(micr_folder, "microscopy.json")
    if os.path.exists(path):
        return

    # Manual fields from YAML
    content = cfg.get("microscopy_json", {}).copy()

    # Auto fields from CZI reader
    content["Manufacturer"]     = manufacturer
    content["IlluminationType"] = illumination
    content["PixelSizeUnits"]   = "um"

    with open(path, "w", encoding="utf-8") as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
    print("micr.json created")

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

def get_json_path(nii_path: Path) -> Path:
    """Returns the JSON sidecar path for a given NIfTI path"""
    return Path(str(nii_path).replace(".nii.gz", ".json").replace(".nii", ".json"))

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