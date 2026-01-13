from __future__ import annotations
from pylibCZIrw import czi as czirw  
from pathlib import Path
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Optional, Tuple, List, Dict
import re


def get_czi_xml(czi_path: Path) -> str:
    """
    Return the metadata XML string from a CZI using pylibCZIrw.

    This function tries multiple common attribute/method names to stay robust
    across pylibCZIrw versions.

    Raises:
        RuntimeError: if the XML metadata cannot be retrieved.
    """
    with czirw.open_czi(str(czi_path)) as doc:
        # Try common attribute names
        for attr in ("metadata", "meta", "xml_metadata", "raw_metadata"):
            if hasattr(doc, attr):
                val = getattr(doc, attr)
                if callable(val):
                    try:
                        val = val()
                    except TypeError:
                        pass
                if isinstance(val, bytes):
                    return val.decode("utf-8", errors="ignore")
                if isinstance(val, str) and val.strip().startswith("<"):
                    return val

        # Try common method names
        for fn in ("get_metadata", "get_xml_metadata", "read_metadata"):
            if hasattr(doc, fn):
                val = getattr(doc, fn)()
                if isinstance(val, bytes):
                    return val.decode("utf-8", errors="ignore")
                if isinstance(val, str) and val.strip().startswith("<"):
                    return val

    raise RuntimeError(f"pylibCZIrw: could not retrieve XML metadata from {czi_path}")

def local(tag: str) -> str:
    """
    Return the local XML tag name without the namespace.

    Example:
        '{http://example}ImageName' -> 'ImageName'
    """
    return tag.split("}")[-1] if "}" in tag else tag


def guess_subject_from_filename(stem: str) -> Optional[str]:
    """
    Guess a subject identifier from the filename (without extension).

    Heuristic:
        - Split by '_' (and '-' treated as '_')
        - Return the first token that contains BOTH letters and digits
        - Token length must be between 6 and 40 characters

    Returns:
        A subject-like token (e.g. 'MTO10092101') or None if not found.
    """
    tokens = [t for t in stem.replace("-", "_").split("_") if t]
    for t in tokens:
        has_a = any(ch.isalpha() for ch in t)
        has_d = any(ch.isdigit() for ch in t)
        if has_a and has_d and 6 <= len(t) <= 40:
            return t
    return None


def guess_sample_from_filename(stem: str) -> Optional[str]:
    """
    Guess a sample label from the filename (without extension).

    Heuristic:
        - Split by '_' (and '-' treated as '_')
        - Identify the subject token first (guess_subject_from_filename)
        - Then scan tokens after the subject token
        - Return the first short alphabetic token (1..8 chars)
        - Normalize 'cortex' -> 'Cx'

    Returns:
        A sample label (e.g. 'Cx') or None if not found.
    """
    tokens = [t for t in stem.replace("-", "_").split("_") if t]

    subj = guess_subject_from_filename(stem)
    start_idx = 0
    if subj and subj in tokens:
        start_idx = tokens.index(subj) + 1

    for t in tokens[start_idx:]:
        if t.isalpha() and 1 <= len(t) <= 8:
            if t.lower() == "cortex":
                return "Cx"
            return t
    return None


def get_imagename_text(root: ET.Element) -> Optional[str]:
    """
    Extract the value of the first <ImageName> tag found in the metadata XML.

    Returns:
        The ImageName string, or None if not found / empty.
    """
    for el in root.iter():
        if local(el.tag) == "ImageName":
            txt = (el.text or "").strip()
            if txt:
                return txt
    return None


def _valid_ymd(y: int, m: int, d: int) -> bool:
    """
    Validate that a (year, month, day) triple is a real calendar date.
    """
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def guess_session_from_imagename(imagename: str) -> Optional[str]:
    """
    Guess a BIDS session label from the ImageName string.

    Supported date patterns in ImageName:
        - YYYYMMDD (e.g. 20230417)
        - DD-MM-YYYY or DD/MM/YYYY (e.g. 17-04-2023)
        - YYYY-MM-DD or YYYY/MM/DD (e.g. 2023-04-17)

    Returns:
        'ses-YYYYMMDD' if a valid date is found, else None.
    """
    for m in re.finditer(r"\b(20\d{2})(\d{2})(\d{2})\b", imagename):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    for m in re.finditer(r"\b(\d{2})[-/](\d{2})[-/](20\d{2})\b", imagename):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    for m in re.finditer(r"\b(20\d{2})[-/](\d{2})[-/](\d{2})\b", imagename):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_ymd(y, mo, d):
            return f"ses-{y:04d}{mo:02d}{d:02d}"

    return None


def extract_microscope_name(root: ET.Element) -> Optional[str]:
    """
    Extract the microscope name from metadata.

    This targets the structure observed in your CZI metadata:
        .../Device with attributes Id='Microscope' and Name='Axio Scan.Z1'

    Returns:
        Microscope name (e.g. 'Axio Scan.Z1') or None if not found.
    """
    for el in root.iter():
        if local(el.tag) == "Device":
            attrs = el.attrib or {}
            if attrs.get("Id") == "Microscope" and attrs.get("Name"):
                return attrs["Name"].strip()
    return None


def extract_channels(root: ET.Element) -> List[str]:
    """
    Extract channel names from metadata.

    This targets the structure observed in your CZI metadata:
        .../Channel elements with attribute Name='DAPI', 'EGFP', 'DsRed', ...

    Returns:
        A list of unique channel names in first-seen order (possibly empty).
    """
    chans: List[str] = []
    for el in root.iter():
        if local(el.tag) == "Channel":
            name = (el.attrib or {}).get("Name")
            if name:
                name = name.strip()
                if name and name not in chans:
                    chans.append(name)
    return chans


def extract_pixel_xy_um(root: ET.Element) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract pixel size for X and Y axes (in micrometers) from metadata.

    This targets Distance nodes:
        <Distance Id="X"> <Value>...</Value> <Unit>...</Unit> </Distance>
        <Distance Id="Y"> ...

    If Unit is missing (unit=None), values are often stored in meters in Zeiss XML.
    In that case, we convert meters -> micrometers by multiplying by 1e6.

    Returns:
        (pixel_size_x_um, pixel_size_y_um), each may be None.
    """
    px = {"X": None, "Y": None}

    for dist in root.iter():
        if local(dist.tag).lower() != "distance":
            continue

        axis = (dist.attrib or {}).get("Id") or (dist.attrib or {}).get("id")
        axis = (axis or "").strip().upper()
        if axis not in ("X", "Y"):
            continue

        value = None
        unit = None
        for ch in list(dist):
            t = local(ch.tag).lower()
            if t == "value":
                try:
                    value = float((ch.text or "").strip())
                except Exception:
                    value = None
            elif t == "unit":
                unit = (ch.text or "").strip()

        if value is None:
            continue

        if unit in (None, "", "m", "meter", "metre"):
            v_um = value * 1e6
        elif unit in ("µm", "um"):
            v_um = value
        elif unit == "nm":
            v_um = value / 1000.0
        else:
            v_um = value

        px[axis] = v_um

    x = None if px["X"] is None else round(px["X"], 6)
    y = None if px["Y"] is None else round(px["Y"], 6)
    return x, y


def make_acq_signature(root: ET.Element) -> Optional[Tuple]:
    """
    Build an acquisition signature used to group files into acq-1, acq-2, ...

    Signature fields:
        (microscope_name, pixel_x_um, pixel_y_um, channels_tuple)

    Returns:
        The signature tuple, or None if microscope name is missing.
    """
    microscope = extract_microscope_name(root)
    if microscope is None:
        return None

    px, py = extract_pixel_xy_um(root)
    chans = tuple(extract_channels(root))
    return (microscope, px, py, chans)


def parse_one_file(czi_path: Path) -> Optional[dict]:
    """
    Parse one CZI file and extract fields required to build the sourcedata tree.

    Extraction rules:
        - subject: from filename (heuristic)
        - sample:  from filename (heuristic)
        - ses:     from ImageName metadata (date parsing)
        - acq_sig: from microscope + pixel size + channels metadata

    Returns:
        A dict with keys: src, subject, sample, ses, acq_sig
        or None if any required field is missing.
    """
    xml = get_czi_xml(czi_path)
    root = ET.fromstring(xml)

    subject = guess_subject_from_filename(czi_path.stem)
    if subject is None:
        return None

    sample = guess_sample_from_filename(czi_path.stem)
    if sample is None:
        return None

    imagename = get_imagename_text(root)
    if imagename is None:
        return None

    ses = guess_session_from_imagename(imagename)
    if ses is None:
        return None

    sig = make_acq_signature(root)
    if sig is None:
        return None

    return {
        "src": czi_path,
        "subject": subject,
        "sample": sample,
        "ses": ses,
        "acq_sig": sig,
    }

def move_file(src: Path, dst: Path) -> None:
    """
    Link our empty BIDS file to the real one in src 
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    dst.symlink_to(src.resolve())


def organize_sourcedata(input_dir: Path, sourcedata_dir: Path, workers: int = 8) -> None:
    """
    Organize all CZI files from input_dir into sourcedata_dir.

    Output structure:
        sourcedata/sub-XX/ses-YYYYMMDD/sample-<sample>/acq-<n>/
            sub-XX_ses-YYYYMMDD_sample-<sample>_acq-<n>_run-YY.czi

    Grouping rules:
        - sub-XX: created per unique subject (sorted for deterministic numbering)
        - ses: extracted from metadata ImageName date
        - sample: extracted from filename
        - acq-N: assigned per unique acquisition signature within (sub, ses, sample)
        - run-YY: incremented within (sub, ses, sample, acq)

    Files missing required fields are skipped (printed as warnings).
    """
    czis = sorted(Path(input_dir).glob("*.czi"))
    if not czis:
        print(f"[INFO] No .czi files in {input_dir}")
        return

    records: List[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(parse_one_file, czi): czi for czi in czis}
        for fut in as_completed(futs):
            czi = futs[fut]
            rec = fut.result()
            if rec is None:
                print(f"[WARN] Missing required fields (subject/sample/ses/acq): {czi.name}")
                continue
            records.append(rec)

    if not records:
        print("[INFO] No usable files.")
        return

    subjects = sorted({r["subject"] for r in records})
    subject_to_sub = {sid: f"sub-{i:02d}" for i, sid in enumerate(subjects, start=1)}

    group_sigs: Dict[Tuple[str, str, str], List[Tuple]] = {}
    for r in records:
        sub = subject_to_sub[r["subject"]]
        key = (sub, r["ses"], r["sample"])
        group_sigs.setdefault(key, [])
        if r["acq_sig"] not in group_sigs[key]:
            group_sigs[key].append(r["acq_sig"])

    for key in group_sigs:
        group_sigs[key] = sorted(group_sigs[key], key=lambda x: str(x))

    run_counter: Dict[Tuple[str, str, str, int], int] = {}

    def sort_key(r: dict):
        sub = subject_to_sub[r["subject"]]
        key3 = (sub, r["ses"], r["sample"])
        acq_num = group_sigs[key3].index(r["acq_sig"]) + 1
        return (sub, r["ses"], r["sample"], acq_num, r["src"].name)

    for r in sorted(records, key=sort_key):
        sub = subject_to_sub[r["subject"]]
        ses = r["ses"]
        sample = r["sample"]

        key3 = (sub, ses, sample)
        acq_num = group_sigs[key3].index(r["acq_sig"]) + 1

        rc_key = (sub, ses, sample, acq_num)
        run_counter[rc_key] = run_counter.get(rc_key, 0) + 1
        run = f"run-{run_counter[rc_key]:02d}"

        dest_dir = Path(sourcedata_dir) / sub / ses / f"sample-{sample}" / f"acq-{acq_num}"
        dest_name = f"{sub}_{ses}_sample-{sample}_acq-{acq_num}_{run}.czi"
        dest_path = dest_dir / dest_name

        move_file(r["src"], dest_path)

    print("[OK] sourcedata organization done.")


def main() -> None:
    """
    Example entry point.
    """
    input_dir = Path("/DATA/mimosa/original-dataset/1-Fenouil-MTO10092101")
    sourcedata_dir = Path("/DATA/mimosa/MIMOSA_BIDS_dataset/sourcedata")
    organize_sourcedata(input_dir, sourcedata_dir, workers=8)


if __name__ == "__main__":
    main()
