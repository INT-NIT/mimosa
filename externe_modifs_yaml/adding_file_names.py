import os
import yaml
from BIDS.czi_reader import MimosaReader
import argparse


def has_dapi_channel(czi_path):
    """
    Opens a CZI file and checks if it contains a DAPI channel.
    Returns True if DAPI is found, False otherwise.
    """
    try:
        with MimosaReader(czi_path) as reader:
            channels = reader.get_channels()
            return any(ch.upper() == "DAPI" for ch in channels)
    except Exception as e:
        print(f"  Error reading {os.path.basename(czi_path)}: {e}")
        return False


def populate_yaml_files(yaml_path, target_sample_id, target_sample_type):
    """
    Scans all CZI files in the folder defined in the YAML,
    filters those with a DAPI channel,
    and writes them only into the sample matching target_sample_id.

    Args:
        yaml_path         : path to the YAML file
        target_sample_id  : sample to fill, e.g. "Cx" or "TC"
        target_sample_type: sample type to set, e.g. "tissue"
    """

    # Load the YAML file
    with open(yaml_path, 'r') as f:
        cfg = yaml.safe_load(f)

    for entry in cfg.get('samples', {}).get('entries', []):
        folder_path = entry['path'].rstrip('/')

        if not os.path.exists(folder_path):
            print(f"Folder not found: {folder_path}")
            continue

        # List and sort all CZI files in the folder
        all_czi = sorted([
            f for f in os.listdir(folder_path)
            if f.endswith('.czi')
        ])

        print(f"\nFolder: {folder_path}")
        print(f"  {len(all_czi)} CZI files found")

        # Keep only files that contain a DAPI channel
        dapi_files = []
        for filename in all_czi:
            full_path = os.path.join(folder_path, filename)
            if has_dapi_channel(full_path):
                dapi_files.append({'filename': filename})
                print(f"  DAPI found in  {filename}")
            else:
                print(f"   NO DAPI Channel in {filename}  ")

        print(f"  → {len(dapi_files)} files with DAPI")

        # Find the sample matching target_sample_id and write files there
        found = False
        for sample in entry.get('samples', []):
            if sample.get('sample_id') == target_sample_id:
                sample['files'] = dapi_files
                print(f"  ->  written into sample '{target_sample_id}'")
                found = True
                break  

        if not found:
            print(f"   sample '{target_sample_id}' not found in this entry")

    with open(yaml_path, 'w') as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)

    print(f"\nYAML updated: {yaml_path}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Populate YAML with CZI files containing DAPI channel")
    parser.add_argument("--yaml",        required=True, help="Path to the YAML file")
    parser.add_argument("--sample_id",   required=True, help="Target sample ID, e.g. 'Cx' or 'TC'")
    args = parser.parse_args()

    populate_yaml_files(args.yaml, args.sample_id)