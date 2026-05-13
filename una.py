import yaml
import math

def expand_slice_ranges(yaml_path: str) -> None:
    """
    Reads a YAML file and for each file entry:
    - If slices = [start, end, step] → expands to list e.g. [2, 28, 2] → [2, 4, 6, ..., 28]
    - If slices is empty, None, or contains NaN → removes the file entry entirely
    Saves the updated YAML in place.
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    for entry in cfg.get("samples", {}).get("entries", []):
        for sample in entry.get("samples", []):
            files = sample.get("files", [])
            updated_files = []

            for file_entry in files:
                slices = file_entry.get("slices")

                # Skip if no slices or NaN
                if slices is None:
                    print(f"  REMOVED (no slices): {file_entry['filename']}")
                    continue

                # Skip if any value is NaN or not a number
                if any(isinstance(s, float) and math.isnan(s) for s in slices):
                    print(f"  REMOVED (NaN slices): {file_entry['filename']}")
                    continue

                # Skip if empty list
                if len(slices) == 0:
                    print(f"  REMOVED (empty slices): {file_entry['filename']}")
                    continue

                # Expand [start, end, step] → full list
                if len(slices) == 3:
                    start, end, step = slices
                    expanded = list(range(int(start), int(end) + 1, int(step)))
                    file_entry["slices"] = expanded
                    print(f"  EXPANDED {file_entry['filename']}: {slices} → {expanded}")

                updated_files.append(file_entry)

            sample["files"] = updated_files
            print(f"  → {len(updated_files)} files kept for {sample['sample_id']}")

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\nYAML updated: {yaml_path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--yaml", required=True, help="Path to YAML file")
    args = parser.parse_args()
    expand_slice_ranges(args.yaml)