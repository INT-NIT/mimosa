import json
import csv
import re
from pathlib import Path
from pylibCZIrw import czi as czirw

# Imports from your base module
from mimosa_bids_builder import extract_subject, find_key_in_dict, to_string

# =========================================================
# 1. ATOMIC EXTRACTION (Animal Info)
# =========================================================

def extract_animal_age(metadata):
    """Extracts age from metadata (BIDS RECOMMENDED)."""
    raw = find_key_in_dict(metadata, "Age") or find_key_in_dict(metadata, "Weight")
    if raw:
        match = re.search(r"(\d+)", to_string(raw))
        return match.group(1) if match else "n/a"
    return "n/a"

def extract_animal_sex(metadata):
    """Extracts sex from metadata (BIDS RECOMMENDED: M/F)."""
    raw = find_key_in_dict(metadata, "Sex") or find_key_in_dict(metadata, "Gender")
    if raw:
        s = to_string(raw).lower()
        if 'f' in s: return "F"
        if 'm' in s: return "M"
    return "n/a"

def extract_animal_species(metadata):
    """Extracts species name (BIDS RECOMMENDED)."""
    raw = find_key_in_dict(metadata, "Species") or find_key_in_dict(metadata, "Organism")
    return to_string(raw) if raw else "n/a"

# =========================================================
# 2. MODULE: DATASET DESCRIPTION (dataset_description.json)
# =========================================================

def write_dataset_description(bids_root):
    """Creates the mandatory dataset_description.json file at the root."""
    file_path = Path(bids_root) / "dataset_description.json"
    description_content = {
        "Name": "Mimosa Axioscan Project",
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "Authors": ["Your Name"],
        "GeneratedBy": [{
            "Name": "Mimosa BIDS Builder",
            "Version": "1.0.0"
        }]
    }
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(description_content, f, indent=4, ensure_ascii=False)

# =========================================================
# 3. MODULE: PARTICIPANTS INFO (TSV & Sidecar JSON)
# =========================================================

def write_participants_table(bids_root, participants_db):
    """Creates the participants.tsv file at the root."""
    file_path = Path(bids_root) / "participants.tsv"
    # Column order is strictly defined by BIDS
    fieldnames = ["participant_id", "species", "age", "sex"]
    
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()
        for sub_id in sorted(participants_db.keys()):
            row = {"participant_id": sub_id, **participants_db[sub_id]}
            writer.writerow(row)

def write_participants_sidecar(bids_root):
    """Creates the participants.json (Sidecar) file at the root."""
    file_path = Path(bids_root) / "participants.json"
    sidecar_content = {
        "species": {"Description": "NCBI Taxonomy binomial name"},
        "age": {"Description": "Age of the participant", "Units": "n/a"},
        "sex": {
            "Description": "Biological sex of the participant",
            "Levels": {"M": "male", "F": "female"}
        }
    }
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(sidecar_content, f, indent=4)

# =========================================================
# 4. GLOBAL ORCHESTRATION (Root Files)
# =========================================================

def build_bids_root_files(source_dir, bids_root):
    """Harvests info and generates all root BIDS metadata files."""
    src_path = Path(source_dir)
    bids_path = Path(bids_root)
    bids_path.mkdir(parents=True, exist_ok=True)

    participants_info = {}

    print(f"--- Scanning files to harvest animal information ---")
    for f in src_path.rglob("*.czi"):
        sub_id = extract_subject(f)
        
        if sub_id not in participants_info:
            participants_info[sub_id] = {"species": "n/a", "age": "n/a", "sex": "n/a"}

        current = participants_info[sub_id]
        if "n/a" in current.values():
            try:
                with czirw.open_czi(str(f)) as doc:
                    meta = doc.metadata
                
                if current["age"] == "n/a": current["age"] = extract_animal_age(meta)
                if current["sex"] == "n/a": current["sex"] = extract_animal_sex(meta)
                if current["species"] == "n/a": current["species"] = extract_animal_species(meta)
            except:
                continue

    print(f"--- Generating BIDS compliant root files ---")
    
    # Writing the 3 root files (Dataset Description, Participants TSV, Participants JSON)
    write_dataset_description(bids_path)
    write_participants_table(bids_path, participants_info)
    write_participants_sidecar(bids_path)

    print(f"\nSUCCESS: BIDS root files are ready in: {bids_path}")

if __name__ == "__main__":
    ORIGINAL_DATA =  "/envau/work/nit/users/boudlal.h/original-dataset"
    BIDS_DIR = "/envau/work/nit/users/boudlal.h/BIDS_dataset"
    build_bids_root_files(ORIGINAL_DATA, BIDS_DIR)