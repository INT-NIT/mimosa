import os
import yaml
import ancpbids.utils


def load_metadata_config(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def create_dataset_description(bids_root: str, cfg: dict) -> None:
   
    path = os.path.join(bids_root, "dataset_description.json")
    if os.path.exists(path):
        return

    dataset_cfg = cfg.get("dataset", {})
    desc = {
        "Name": dataset_cfg.get("name", "bids_dataset"),
        "BIDSVersion": dataset_cfg.get("bids_version", "1.8.0"),
        "DatasetType": "raw",
    }
    ancpbids.utils.write_contents(path, desc)
    print("dataset_description.json cree")


def create_participants_files(bids_root: str, cfg: dict) -> None:
    
    # 1) participants.json
    json_path = os.path.join(bids_root, "participants.json")
    if not os.path.exists(json_path):
        participants_json = cfg.get("participants_json", {})
        ancpbids.utils.write_contents(json_path, participants_json)
        print("participants.json cree")

    # 2) participants.tsv
    tsv_path = os.path.join(bids_root, "participants.tsv")
    if os.path.exists(tsv_path):
        return

    cols = cfg.get("participants_tsv_columns", [])
    rows = cfg.get("participants", [])

    if not cols:
        # fallback minimal
        cols = ["participant_id"]

    lines = ["\t".join(cols)]
    for r in rows:
        line = []
        for c in cols:
            v = r.get(c, "n/a")
            line.append(str(v))
        lines.append("\t".join(line))

    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("participants.tsv cree")


def create_derivatives_descriptions(bids_root: str, cfg: dict) -> None:
   
    derivs = cfg.get("derivatives", {})
    bids_version = cfg.get("dataset", {}).get("bids_version", "1.8.0")

    for pipeline, info in derivs.items():
        deriv_path = os.path.join(bids_root, "derivatives", pipeline)
        os.makedirs(deriv_path, exist_ok=True)

        desc_path = os.path.join(deriv_path, "dataset_description.json")
        if os.path.exists(desc_path):
            continue

        desc = {
            "Name": info.get("name", pipeline),
            "BIDSVersion": bids_version,
            "DatasetType": "derivative",
            "GeneratedBy": [
                {
                    "Name": info.get("generated_by_name", pipeline),
                    "Version": info.get("version", "1.0"),
                    "Description": info.get("description", ""),
                }
            ],
            "SourceDatasets": [{"URL": "../..", "Version": info.get("source_version", "1.0")}],
        }

        ancpbids.utils.write_contents(desc_path, desc)
        print(f"dataset_description.json cree pour derivative {pipeline}")


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


def write_micr_sidecar_json(image_path: str, meta: dict) -> None:
    json_path = os.path.splitext(image_path)[0] + ".json"
    ancpbids.utils.write_contents(json_path, meta)
    print(f"sidecar cree: {os.path.basename(json_path)}")