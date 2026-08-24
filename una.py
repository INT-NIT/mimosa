import yaml
import math


INVALID_STRINGS = {"", "nan", "none", "null", "na", "n/a"}


def is_invalid_value(value) -> bool:
    """
    Return True if value is None, NaN, empty string, 'nan', 'none', etc.
    """
    if value is None:
        return True

    if isinstance(value, float) and math.isnan(value):
        return True

    if isinstance(value, str):
        return value.strip().lower() in INVALID_STRINGS

    return False


def to_int(value, filename: str) -> int:
    """
    Convert a slice value to int.

    Accepted:
        452
        "452"

    Rejected:
        "x320"
        "452i"
        "abc"
        45.5
    """
    if is_invalid_value(value):
        raise ValueError(f"invalid slice value {value!r}")

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError(f"non-integer slice value {value!r}")

    if isinstance(value, str):
        value_clean = value.strip()

        if value_clean.isdigit():
            return int(value_clean)

        raise ValueError(
            f"invalid slice value {value!r}; only integers are accepted"
        )

    raise ValueError(f"invalid slice value type {value!r}")


def parse_slices(file_entry: dict) -> tuple[list[int], tuple[int, int, int]]:
    """
    Parse one file slices field.

    Expected format:
        slices: [start, end, step]

    Example:
        [2, 28, 2] -> [2, 4, 6, ..., 28]

    Returns:
        expanded_slices, (start, end, step)
    """
    filename = file_entry.get("filename", "<unknown>")
    slices = file_entry.get("slices")

    if slices is None:
        raise ValueError("no slices")

    if not isinstance(slices, list):
        raise ValueError("slices must be a list")

    if len(slices) == 0:
        raise ValueError("empty slices")

    if any(is_invalid_value(s) for s in slices):
        raise ValueError(f"invalid/NaN slices {slices!r}")

    values = [to_int(s, filename) for s in slices]

    if len(values) != 3:
        raise ValueError(f"expected [start, end, step], got {values}")

    start, end, step = values

    if step <= 0:
        raise ValueError(f"invalid range {values}: step must be > 0")

    if start > end:
        raise ValueError(f"invalid range {values}: start > end")

    expanded = list(range(start, end + 1, step))

    return expanded, (start, end, step)


def expand_slice_ranges(yaml_path: str) -> None:
    """
    Reads a YAML file and for each file entry:

    - If slices = [start, end, step], expands to:
        [start, start+step, ..., end]

    - If slices is empty, None, or contains NaN:
        removes the file entry

    - If slices contains invalid values like x320 or 452i:
        removes the file entry

    - If range is impossible like [392, 3, 2]:
        removes the file entry

    - If a range strongly overlaps with the next valid file range:
        corrects the current end.

        Example:
            current [392, 934, 2]
            next    [396, 398, 2]

        becomes:
            current [392, 394, 2]

    - If current end == next start:
        keeps both, because this can be valid in your data.

        Example:
            current [492, 494, 2]
            next    [494, 498, 2]

        remains unchanged.

    Saves the updated YAML in place.
    """

    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    for entry in cfg.get("samples", {}).get("entries", []):
        for sample in entry.get("samples", []):
            files = sample.get("files", [])

            valid_entries = []

            # 1. First pass: remove invalid files
            for file_entry in files:
                filename = file_entry.get("filename", "<unknown>")

                try:
                    expanded, range_info = parse_slices(file_entry)

                except ValueError as e:
                    print(f"  REMOVED ({e}): {filename}")
                    continue

                valid_entries.append({
                    "file_entry": file_entry,
                    "filename": filename,
                    "expanded": expanded,
                    "range": range_info,
                })

            # 2. Keep original YAML order
            updated_files = []

            for idx, item in enumerate(valid_entries):
                file_entry = item["file_entry"]
                filename = item["filename"]

                start, end, step = item["range"]

                remove_current = False

                # Compare with next valid file
                if idx + 1 < len(valid_entries):
                    next_item = valid_entries[idx + 1]

                    next_filename = next_item["filename"]
                    next_start, next_end, next_step = next_item["range"]

                    # Strong overlap only.
                    # We fix only when current end is strictly greater than next start.
                    #
                    # Accepted:
                    #   current [492, 494, 2]
                    #   next    [494, 498, 2]
                    #
                    # Fixed:
                    #   current [392, 934, 2]
                    #   next    [396, 398, 2]
                    if end > next_start:
                        corrected_end = next_start - step

                        if corrected_end < start:
                            print(
                                f"  REMOVED (cannot fix overlap): {filename}\n"
                                f"    current: [{start}, {end}, {step}]\n"
                                f"    next:    {next_filename} [{next_start}, {next_end}, {next_step}]\n"
                                f"    problem: corrected end {corrected_end} < start {start}"
                            )
                            remove_current = True

                        else:
                            print(
                                f"  FIXED (range overlaps next file): {filename}\n"
                                f"    current before: [{start}, {end}, {step}]\n"
                                f"    next:           {next_filename} [{next_start}, {next_end}, {next_step}]\n"
                                f"    current after:  [{start}, {corrected_end}, {step}]"
                            )
                            end = corrected_end

                    # Warning only: no modification.
                    expected_next_start = end + step

                    if not remove_current and next_start != expected_next_start:
                        print(
                            f"  WARNING (gap or irregular continuity): {filename} -> {next_filename}\n"
                            f"    expected next start: {expected_next_start}, got: {next_start}"
                        )

                if remove_current:
                    continue

                expanded = list(range(start, end + 1, step))

                if len(expanded) == 0:
                    print(f"  REMOVED (no slices after correction): {filename}")
                    continue

                file_entry["slices"] = expanded
                updated_files.append(file_entry)

                print(f"  EXPANDED {filename}: [{start}, {end}, {step}] → {expanded}")

            sample["files"] = updated_files
            print(f"  → {len(updated_files)} files kept for {sample.get('participant_id', 'unknown')}")
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(
            cfg,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False
        )

    print(f"\nYAML updated: {yaml_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--yaml", required=True, help="Path to YAML file")
    args = parser.parse_args()

    expand_slice_ranges(args.yaml)