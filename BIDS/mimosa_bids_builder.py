import json
import re
import shutil
from pathlib import Path
from pylibCZIrw import czi as czirw
import os 
# =========================================================
# HELPERS
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

# =========================================================
# EXTRACTIONS
# =========================================================

def extract_subject(file_path):
    """Dynamically extracts subject name from parent folder name."""
    folder_name = file_path.parent.name
    parts = re.split(r'[-_]', folder_name)
    
    # Try to find a purely alphabetical word (e.g., Marmot)
    for p in parts:
        if p.isalpha() and len(p) > 2:
            return f"sub-{p.capitalize()}"
            
    # Fallback: find first alphanumeric block and strip digits
    for p in parts:
        if any(c.isalpha() for c in p) and len(p) > 2:
            clean = re.sub(r'^[0-9]+|[0-9]+$', '', p)
            if len(clean) > 2:
                return f"sub-{clean.capitalize()}"

    return f"sub-{folder_name}"

def extract_session(metadata):
    raw_date = find_key_in_dict(metadata, "AcquisitionDateAndTime") or find_key_in_dict(metadata, "CreationDate")
    if raw_date:
        match = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", to_string(raw_date))
        if match:
            y, m, d = match.groups()
            return f"ses-{y}{m}{d}"
    return "ses-01"

def extract_sample(file_name):
    return "Cx" if any(x in file_name.lower() for x in ["cortex", "cx"]) else "Sam"

def extract_microscope(metadata):
    devices = find_key_in_dict(metadata, "Device")
    for d in (devices if isinstance(devices, list) else [devices] if devices else []):
        if to_string(d.get("@Id")) == "Microscope":
            return to_string(d.get("@Name"))
    return "Unknown"

# =========================================================
# CORE LOGIC
# =========================================================

def get_acq_index(info, acq_map):
    group_key = (info['sub'], info['ses'], info['sample'])
    if group_key not in acq_map:
        acq_map[group_key] = []
    if info['acq_sig'] not in acq_map[group_key]:
        acq_map[group_key].append(info['acq_sig'])
    return acq_map[group_key].index(info['acq_sig']) + 1

def parse_czi(file_path):
    try:
        with czirw.open_czi(str(file_path)) as doc:
            meta = doc.metadata
    except: return None

    scope = extract_microscope(meta)
    scaling = find_key_in_dict(meta, "Scaling")
    
    return {
        "path": file_path,
        "sub": extract_subject(file_path),
        "ses": extract_session(meta),
        "sample": extract_sample(file_path.name),
        "acq_sig": f"{scope}_{str(scaling)[:30]}",
        "full_metadata": meta
    }

def organize_files(src, dst):
    src_path, dst_path = Path(src), Path(dst)
    acq_map, run_counts = {}, {}

    for f in src_path.rglob("*.czi"):
        info = parse_czi(f)
        if not info: continue

        acq_id = get_acq_index(info, acq_map)
        run_key = (info['sub'], info['ses'], info['sample'], acq_id)
        run_counts[run_key] = run_counts.get(run_key, 0) + 1
        
        # Build BIDS path
        sub, ses, sam = info['sub'], info['ses'], info['sample']
        folder = dst_path / sub / ses / f"sample-{sam}" / f"acq-{acq_id}"
        folder.mkdir(parents=True, exist_ok=True)

        base_name = f"{sub}_{ses}_sample-{sam}_acq-{acq_id}_run-{run_counts[run_key]:02d}"
        
        # Handle .czi file
        czi_dest = folder / f"{base_name}.czi"
        if not czi_dest.exists():
            try:
                os.link(str(f), str(czi_dest)) # Tente un Hard Link
            except Exception as e:
                # Instead of copying, we print a clear error and stop for this file
                print(f"ERROR: Could not create symlink for {f.name}.")
                print(f"Reason: {e}")
                print("Check your permissions or if the filesystem supports symlinks.")

        # Handle .json metadata
        json_dest = folder / f"{base_name}_metadata.json"
        with open(json_dest, 'w', encoding='utf-8') as jf:
            json.dump(info['full_metadata'], jf, indent=4, ensure_ascii=False)
        
        print(f"Processed: {base_name}")

if __name__ == "__main__":
    SOURCE_DIR = "/envau/work/nit/users/boudlal.h/original-dataset"
    OUTPUT_DIR = "/envau/work/nit/users/boudlal.h/BIDS_dataset/sourcedata"
    organize_files(SOURCE_DIR, OUTPUT_DIR)
     #"/envau/work/nit/users/boudlal.h/BIDS_dataset"