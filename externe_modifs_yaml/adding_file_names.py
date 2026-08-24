import sys
sys.path.append('/DATA/mimosa/mimosa')
import os
import re
import yaml
from BIDS.czi_reader import MimosaReader
import argparse


def has_dapi_channel(czi_path):
    try:
        with MimosaReader(czi_path) as reader:
            summary = reader.get_summary()
            channels = (
                summary["full_meta"]
                .get("ImageDocument", {})
                .get("Metadata", {})
                .get("DisplaySetting", {})
                .get("Channels", {})
                .get("Channel", [])
            )
            if isinstance(channels, dict):
                channels = [channels]
            for ch in channels:
                if ch.get("@Name", "").upper() == "DAPI":
                    return True
        return False
    except Exception as e:
        print(f"  Error reading {os.path.basename(czi_path)}: {e}")
        return False


def populate_yaml_files(yaml_path, folder_path, target_sample_id, sample_type=None, sections_interval=None):

    with open(yaml_path, 'r') as f:
        cfg = yaml.safe_load(f)

    folder_path = folder_path.rstrip('/')

    if not os.path.exists(folder_path):
        print(f"Folder not found: {folder_path}")
        return

    # Get subject from folder name
    parent_name = os.path.basename(os.path.dirname(folder_path))
    subject = re.sub(r'^\d+-', '', parent_name)  # "8-Una" → "Una"
    participant_id = f"sub-{subject}"
    print(f"  -> subject: '{subject}'")
    print(f"  -> participant_id: '{participant_id}'")

    # List all CZI files
    all_czi = sorted([f for f in os.listdir(folder_path) if f.endswith('.czi')])
    print(f"\nFolder: {folder_path} — {len(all_czi)} CZI files found")

    # Keep only files with DAPI, add empty slices field under each file
    dapi_files = []
    for filename in all_czi:
        if has_dapi_channel(os.path.join(folder_path, filename)):
            dapi_files.append({
                'filename': filename,
                'slices':   [],   # to be filled manually later
            })
            print(f"  DAPI FOUND IN {filename}")
        else:
            print(f"  NOT FOUND DAPI IN {filename}")

    print(f"  → {len(dapi_files)} files with DAPI")

    # Find or create the entry matching folder_path in the YAML
    entries = cfg.get('samples', {}).get('entries') or []
    target_entry = None
    for entry in entries:
        if entry['path'].rstrip('/') == folder_path:
            target_entry = entry
            break

    # If entry does not exist, create it
    if target_entry is None:
        target_entry = {'path': folder_path, 'samples': []}
        entries.append(target_entry)
        cfg.setdefault('samples', {})['entries'] = entries
        print(f"  -> created new entry for path '{folder_path}'")

    # Get existing samples list (handle None case)
    samples = target_entry.get('samples') or []

    # Build the sample dict with sections_interval before sample_id
    new_sample = {
        'sections_interval': sections_interval,
        'sample_id':        target_sample_id,
        'participant_id':   participant_id,
        'sample_type':      sample_type,
        'files':            dapi_files,
    }

    # Check if target sample already exists
    target_found = False
    for i, sample in enumerate(samples):
        yaml_id   = sample.get('sample_id', '').replace('sample-', '').upper()
        target_id = target_sample_id.replace('sample-', '').upper()
        if yaml_id == target_id:
            # Keep existing sections_interval if not provided
            if sections_interval is None:
                new_sample['sections_interval'] = sample.get('sections_interval')
            samples[i] = new_sample
            print(f"  -> updated sample '{target_sample_id}'")
            target_found = True
            break

    # If sample does not exist yet, create it
    if not target_found:
        samples.append(new_sample)
        print(f"  -> created sample '{target_sample_id}'")

    target_entry['samples'] = samples

    with open(yaml_path, 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\nYAML updated: {yaml_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--yaml",             required=True,  help="Path to YAML file")
    parser.add_argument("--path",             required=True,  help="Path to the folder containing CZI files")
    parser.add_argument("--sample_id",        required=True,  help="e.g. 'sample-Cx'")
    parser.add_argument("--sample_type",      required=False, help="e.g. 'tissue'")
    parser.add_argument("--sections_interval", required=False, type=int, help="e.g. 8 means 1 section every 8")
    args = parser.parse_args()
    populate_yaml_files(args.yaml, args.path, args.sample_id, args.sample_type, args.sections_interval)

"""
python adding_file_names.py \
    --yaml /DATA/mimosa/mimosa/metadata.yml \
    --path /envau/work/invibe/USERS/IBOS/data/Marmoset/lames/0-Originals/8-Una/UNA \
    --sample_id sample-Cx \
    --sample_type tissue \
    --sections_interval 8
"""