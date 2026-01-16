import json
import csv
import re
from pathlib import Path
from pylibCZIrw import czi as czirw

# =========================================================
# REUSE YOUR HELPERS
# =========================================================

def find_key_in_dict(data, target_key):
    if isinstance(data, dict):
        for k, v in data.items():
            if k.lower() == target_key.lower(): return v
            res = find_key_in_dict(v, target_key)
            if res: return res
    elif isinstance(data, list):
        for item in data:
            res = find_key_in_dict(item, target_key)
            if res: return res
    return None

def to_string(value):
    if value is None: return ""
    if isinstance(value, list) and value: return to_string(value[0])
    if isinstance(value, dict):
        return to_string(value.get("#text") or value.get("Value") or value.get("@Value"))
    return str(value).strip()

def extract_subject(file_path):
    folder_name = file_path.parent.name
    parts = re.split(r'[-_]', folder_name)
    for p in parts:
        if p.isalpha() and len(p) > 2: return f"sub-{p.capitalize()}"
    for p in parts:
        if any(c.isalpha() for c in p) and len(p) > 2:
            clean = re.sub(r'^[0-9]+|[0-9]+$', '', p)
            if len(clean) > 2: return f"sub-{clean.capitalize()}"
    return f"sub-{folder_name}"

# =========================================================
# NEW EXTRACTION LOGIC (TSV FIELDS)
# =========================================================

def extract_participant_traits(metadata):
    """Search for BIDS traits in CZI metadata."""
    traits = {"age": "n/a", "sex": "n/a", "species": "n/a"}
    
    # 1. Species search
    spec = get_val(metadata, ["Species", "Organism", "Taxon"])
    if spec: traits["species"] = spec

    # 2. Sex search (Standardizing to male/female/other)
    s = str(get_val(metadata, ["Sex", "Gender"])).lower()
    if 'f' in s: traits["sex"] = "female"
    elif 'm' in s: traits["sex"] = "male"

    # 3. Age search
    a = get_val(metadata, ["Age", "Weight"])
    if a:
        match = re.search(r"(\d+)", str(a))
        if match: traits["age"] = match.group(1)

    return traits

def get_val(metadata, keys):
    val = find_key_in_dict(metadata, keys[0]) # Simplified search for demo
    # For robustness, we could iterate keys but find_key_in_dict is already recursive
    for k in keys:
        res = find_key_in_dict(metadata, k)
        if res: return to_string(res)
    return None

# =========================================================
# MAIN GENERATOR
# =========================================================

def generate_root_files(src_dir, bids_root, project_name="Mimosa Project"):
    src_path, bids_path = Path(src_dir), Path(bids_root)
    bids_path.mkdir(parents=True, exist_ok=True)
    
    subjects_db = {}

    print("Analyzing files for participants table...")
    for f in src_path.rglob("*.czi"):
        sub_id = extract_subject(f)
        
        # If we already have full info for this subject, skip reading metadata
        if sub_id in subjects_db and "n/a" not in subjects_db[sub_id].values():
            continue

        try:
            with czirw.open_czi(str(f)) as doc:
                meta = doc.metadata
            traits = extract_participant_traits(meta)
            
            if sub_id not in subjects_db:
                subjects_db[sub_id] = traits
            else:
                # Merge: replace n/a with found values from other files
                for k in traits:
                    if subjects_db[sub_id][k] == "n/a":
                        subjects_db[sub_id][k] = traits[k]
        except: continue

    # 1. Create participants.tsv (TAB separated)
    tsv_file = bids_path / "participants.tsv"
    with open(tsv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["participant_id", "age", "sex", "species"], delimiter='\t')
        writer.writeheader()
        for sid, info in sorted(subjects_db.items()):
            writer.writerow({"participant_id": sid, **info})

    # 2. Create participants.json
    json_sidecar = {
        "age": {"Description": "Age of the participant", "Units": "months"},
        "sex": {"Description": "Sex", "Levels": {"male": "male", "female": "female"}},
        "species": {"Description": "Binomial species name from NCBI Taxonomy"}
    }
    with open(bids_path / "participants.json", 'w') as f:
        json.dump(json_sidecar, f, indent=4)

    # 3. Create dataset_description.json
    desc = {
        "Name": project_name,
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "Authors": ["Your Name"]
    }
    with open(bids_path / "dataset_description.json", 'w') as f:
        json.dump(desc, f, indent=4)

    print(f"BIDS root files created in {bids_root}")

if __name__ == "__main__":
    generate_root_files("/DATA/mimosa/original-dataset", "/DATA/mimosa/BIDS_dataset")