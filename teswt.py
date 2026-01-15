#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

# ---------- CZI XML readers (try aicspylibczi then czifile) ----------

def get_czi_xml(czi_path: Path) -> str:
    """
    Return CZI metadata as XML string.
    Tries aicspylibczi first, then czifile.
    """
    # Try aicspylibczi
    try:
        from aicspylibczi import CziFile  # type: ignore
        return CziFile(str(czi_path)).meta
    except Exception:
        pass

    # Fallback: czifile
    try:
        import czifile  # type: ignore
        with czifile.CziFile(str(czi_path)) as czi:
            return czi.metadata()
    except Exception as e:
        raise RuntimeError(
            f"Unable to read CZI metadata XML for {czi_path}. "
            f"Install aicspylibczi or czifile. Last error: {e}"
        )

# ---------- XML helpers ----------

TARGET_TEXT_TAGS = {"SampleName", "ImageName", "Experiment"}

def extract_text_fields(xml_str: str, target_tags=TARGET_TEXT_TAGS) -> dict[str, list[str]]:
    """
    Extract all occurrences of certain tags (by localname) from XML.
    Returns {tag: [values...]} with duplicates removed preserving order.
    """
    root = ET.fromstring(xml_str)
    out: dict[str, list[str]] = {t: [] for t in target_tags}

    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag in target_tags:
            txt = (el.text or "").strip()
            if txt and txt not in out[tag]:
                out[tag].append(txt)

    return {k: v for k, v in out.items() if v}

def extract_scaling_um(xml_str: str) -> dict[str, float]:
    """
    Best-effort extraction of pixel/voxel scaling from Zeiss XML.
    Returns e.g. pixel_size_X_um / pixel_size_Y_um / pixel_size_Z_um when found.
    """
    root = ET.fromstring(xml_str)
    out: dict[str, float] = {}

    for dist in root.iter():
        tag = dist.tag.split("}")[-1] if "}" in dist.tag else dist.tag
        if tag.lower() == "distance":
            axis = dist.attrib.get("Id") or dist.attrib.get("id") or dist.attrib.get("Dimension") or ""
            axis = axis.strip().upper()
            if axis not in {"X", "Y", "Z"}:
                continue

            value = None
            unit = None
            for child in dist:
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ctag.lower() == "value":
                    try:
                        value = float((child.text or "").strip())
                    except Exception:
                        value = None
                elif ctag.lower() == "unit":
                    unit = (child.text or "").strip()

            if value is not None:
                if unit in {"µm", "um", "micrometer", "micrometre"} or unit in {None, ""}:
                    out[f"pixel_size_{axis}_um"] = value
                elif unit == "nm":
                    out[f"pixel_size_{axis}_um"] = value / 1000.0
                elif unit == "mm":
                    out[f"pixel_size_{axis}_um"] = value * 1000.0

    return out

def extract_channel_names(xml_str: str) -> list[str]:
    """
    Best-effort extraction of channel names/dyes.
    We search for tags like 'DyeName', 'Fluor', 'Name' under 'Channel'.
    """
    root = ET.fromstring(xml_str)
    channel_names: list[str] = []

    for el in root.iter():
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag.lower() == "channel":
            candidates = []
            for child in el.iter():
                ctag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if ctag in {"DyeName", "Fluor", "Name", "ShortName"}:
                    txt = (child.text or "").strip()
                    if txt:
                        candidates.append(txt)
            if candidates:
                channel_names.append(candidates[0])

    uniq = []
    for n in channel_names:
        if n not in uniq:
            uniq.append(n)
    return uniq

# ---------- Subject / Sample / Session helpers ----------

SUBJECT_REGEX = re.compile(r"(MTO\d+|MIO\d+)", re.IGNORECASE)
SAMPLE_REGEX = re.compile(r"(?:^|_)(Cx|Cortex|Hip|Str|CB)(?:_|$)", re.IGNORECASE)

def _join_text_fields(text_fields: dict[str, list[str]]) -> str:
    if not text_fields:
        return ""
    return " | ".join([" ".join(v) for v in text_fields.values() if v])

def guess_subject_id(text_fields: dict[str, list[str]], filename_stem: str) -> str | None:
    blob = _join_text_fields(text_fields)
    m = SUBJECT_REGEX.search(blob)
    if m:
        return m.group(1)

    m2 = SUBJECT_REGEX.search(filename_stem)
    return m2.group(1) if m2 else None

def guess_sample_label(filename_stem: str, text_fields: dict[str, list[str]]) -> str | None:
    m = SAMPLE_REGEX.search(filename_stem)
    if m:
        return m.group(1)

    blob = _join_text_fields(text_fields)
    m2 = SAMPLE_REGEX.search(blob)
    return m2.group(1) if m2 else None

def extract_acquisition_date(xml_str: str) -> str | None:
    """
    Best-effort: find YYYY-MM-DD (optionally with time) in XML.
    Returns YYYY-MM-DD if found.
    """
    m = re.search(r"(\d{4}-\d{2}-\d{2})(?:[T\s]\d{2}:\d{2}:\d{2})?", xml_str)
    return m.group(1) if m else None

def guess_session_label(xml_str: str, fixed_ses: str | None = None) -> str:
    """
    If fixed_ses is provided (e.g. 'ses-01'), always return it.
    Else try to build ses-YYYYMMDD from date in XML; fallback to 'unknown'.
    """
    if fixed_ses:
        return fixed_ses

    date = extract_acquisition_date(xml_str)
    if not date:
        return "unknown"
    return "ses-" + date.replace("-", "")

# ---------- Common-metadata computation ----------

def compute_common(per_file: dict[str, dict]) -> dict:
    """
    per_file: {filename: {key: value}}
    Return keys whose values are identical across all files.
    For list-values, we require exact equality.
    """
    if not per_file:
        return {}

    files = list(per_file.keys())
    common = {}

    all_keys = set()
    for f in files:
        all_keys.update(per_file[f].keys())

    for k in sorted(all_keys):
        vals = [per_file[f].get(k, None) for f in files]
        first = vals[0]
        if all(v == first for v in vals):
            common[k] = first

    return common

# ---------- Main ----------

def main():
    parser = argparse.ArgumentParser(
        description="Extract per-file and common metadata from all CZI files in a folder."
    )
    parser.add_argument("-i", "--input", required=True, help="Input folder containing .czi files (recursively).")
    parser.add_argument("-o", "--output", required=True, help="Output folder to write JSON reports.")
    parser.add_argument("--max-files", type=int, default=0, help="If >0, limit number of CZI processed (debug).")
    parser.add_argument("--fixed-ses", type=str, default=None, help="Force session label (e.g., ses-01).")
    args = parser.parse_args()

    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    czis = sorted(in_dir.rglob("*.czi"))
    if args.max_files and args.max_files > 0:
        czis = czis[: args.max_files]

    if not czis:
        print(f"[INFO] No .czi files found under: {in_dir}")
        return

    per_file: dict[str, dict] = {}
    errors = []

    for czi in czis:
        try:
            xml = get_czi_xml(czi)

            text_fields = extract_text_fields(xml)
            scaling = extract_scaling_um(xml)
            channels = extract_channel_names(xml)

            filename_stem = czi.stem
            subject_id = guess_subject_id(text_fields, filename_stem)
            sample_label = guess_sample_label(filename_stem, text_fields)
            session_label = guess_session_label(xml, fixed_ses=args.fixed_ses)

            record = {}

            # text fields (flatten)
            for k, v in text_fields.items():
                record[k] = v[0] if len(v) == 1 else v

            # scaling + channels
            record.update(scaling)
            if channels:
                record["channel_names"] = channels

            # subject / sample / session
            record["subject_id"] = subject_id if subject_id else "not_found"
            record["sample_label"] = sample_label if sample_label else "not_found"
            record["session_label"] = session_label

            per_file[str(czi.relative_to(in_dir))] = record

            print(f"[OK] {czi.name} | subject={record['subject_id']} | sample={record['sample_label']} | session={record['session_label']}")
        except Exception as e:
            errors.append({"file": str(czi), "error": str(e)})
            print(f"[ERR] {czi.name}: {e}")

    common = compute_common(per_file)

    # Write outputs
    with open(out_dir / "per_file_metadata.json", "w", encoding="utf-8") as f:
        json.dump(per_file, f, indent=2, ensure_ascii=False)

    with open(out_dir / "common_metadata.json", "w", encoding="utf-8") as f:
        json.dump(common, f, indent=2, ensure_ascii=False)

    with open(out_dir / "errors.json", "w", encoding="utf-8") as f:
        json.dump(errors, f, indent=2, ensure_ascii=False)

    print("\n=== SUMMARY ===")
    print(f"Processed: {len(per_file)} files")
    print(f"Errors:    {len(errors)}")
    print(f"Wrote:     {out_dir / 'common_metadata.json'}")
    print(f"Wrote:     {out_dir / 'per_file_metadata.json'}")
    if errors:
        print(f"Wrote:     {out_dir / 'errors.json'}")

if __name__ == "__main__":
    main()
