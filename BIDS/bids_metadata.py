import os
import yaml
import json  


def load_metadata_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def create_dataset_description(bids_root: str, cfg: dict) -> None:
    
    path = os.path.join(bids_root, "dataset_description.json")
    if os.path.exists(path):
        return

    # on prend directement ce qui est dans le YAML, pas besoin de reconstruire
    desc = cfg.get("dataset_description", {})
    
    if not desc:
        raise ValueError("Key dataset_description missing in YAML ")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(desc, f, indent=2, ensure_ascii=False)
    
    print("dataset_description.json created")

def create_participants_files(bids_root: str, cfg: dict) -> None:

    # participants.json  dump directly from YAML
    json_path = os.path.join(bids_root, "participants.json")
    if not os.path.exists(json_path):
        participants_json = cfg.get("participants_json", {})
        if not participants_json:
            raise ValueError("Key participants_json missing in YAML")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(participants_json, f, indent=2, ensure_ascii=False)
        print("participants.json created")

    # participants.tsv  columns and rows come directly from YAML
    tsv_path = os.path.join(bids_root, "participants.tsv")
    if os.path.exists(tsv_path):
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
        deriv_path = os.path.join(bids_root, "derivatives", pipeline)
        os.makedirs(deriv_path, exist_ok=True)

        desc_path = os.path.join(deriv_path, "dataset_description.json")
        if os.path.exists(desc_path):
            continue

        # dump directly from YAML — no reconstruction needed
        desc = info.get("dataset_description", {})
        if not desc:
            raise ValueError(f"Key 'dataset_description' missing for derivative '{pipeline}' in YAML")

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

    print(f"sessions.tsv cree: sub-{subject}/sessions.tsv")

def write_samples_tsv(bids_root: str, cfg: dict, rows: list[dict]) -> None:
    """
    Writes samples.tsv , columns and sample details come from YAML.
    Adding a column in YAML automatically adds it in the TSV.
    """
    path = os.path.join(bids_root, "samples.tsv")

    samples_section = cfg.get("samples")
    if not samples_section:
        raise ValueError("Key 'samples' missing in YAML")

    cols = samples_section.get("columns")
    if not cols:
        raise ValueError("Key 'columns' missing in samples section of YAML")

    samples_cfg = {}
    for entry in samples_section.get("entries", []):
        subject = entry["subject"]
        for s in entry.get("samples", []):
            key = (subject, s["sample_id"])
            samples_cfg[key] = s

    existing = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f.readlines()[1:]:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    existing.add((parts[0], parts[1]))

    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("\t".join(cols) + "\n")

    new_lines = []
    for r in rows:
        key = (r["sample_id"], r["participant_id"])
        if key in existing:
            continue
        existing.add(key)

        subject_name = r["participant_id"].replace("sub-", "")
        cfg_row = samples_cfg.get((subject_name, r["sample_id"]), {})

        merged = {**r, **cfg_row}

        line = "\t".join(str(merged.get(c, "n/a")) for c in cols)
        new_lines.append(line)

    if new_lines:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")

    print("samples.tsv updated")

def write_micr_sidecar_json(image_path: str, meta: dict) -> None:
    """writes the sidecar JSON file for a given image"""
    json_path = os.path.splitext(image_path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"sidecar created: {os.path.basename(json_path)}")