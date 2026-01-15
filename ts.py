from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET
from collections import defaultdict

# =========================
# CONFIG
# =========================
CZI_PATH = Path("/DATA/mimosa/original-dataset/1-Fenouil-MTO10092101/MTO10092101_Cx_264-272.czi")  # <-- change this
MAX_HITS_PER_KEYWORD = 30                        # limit prints to avoid spam


# =========================
# Read XML from CZI
# =========================
def get_czi_xml(czi_path: Path) -> str:
    """Return metadata XML string from a CZI file."""
    try:
        from aicspylibczi import CziFile  # type: ignore
        return CziFile(str(czi_path)).meta
    except Exception:
        pass

    try:
        import czifile  # type: ignore
        with czifile.CziFile(str(czi_path)) as czi:
            return czi.metadata()
    except Exception as e:
        raise RuntimeError(
            f"Cannot read metadata XML from {czi_path}. "
            f"Install aicspylibczi or czifile. Error: {e}"
        )


# =========================
# Pretty helpers
# =========================
def local_name(tag: str) -> str:
    """Remove XML namespace: '{ns}Tag' -> 'Tag'."""
    return tag.split("}")[-1] if "}" in tag else tag

def elem_path(stack: list[str]) -> str:
    """Build a readable XML path from tag stack."""
    return "/".join(stack)

def shorten(s: str, n: int = 180) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 3] + "..."


# =========================
# Main inspection
# =========================
def inspect(xml_str: str) -> None:
    root = ET.fromstring(xml_str)

    # 1) Quick top-level info
    print("\n=== QUICK FIELDS (if present) ===")
    for key in ["SampleName", "ImageName", "Experiment"]:
        vals = find_text_by_tag(root, key)
        print(f"{key}: {vals[:5] if vals else 'NOT FOUND'}")

    # 2) Search by keywords (dynamic)
    keywords = {
        "DATE/TIME": ["date", "time", "timestamp", "created", "acquisition", "start"],
        "INSTRUMENT": ["instrument", "microscope", "device", "manufacturer", "model", "objective"],
        "SCALING": ["scaling", "distance", "voxel", "pixel", "resolution", "size", "spacing", "unit"],
        "CHANNELS": ["channel", "dye", "fluor", "wavelength", "laser", "emission", "excitation", "stain"],
        "SCENES": ["scene", "tile", "roi", "bounding", "mosaic"],
    }

    print("\n=== KEYWORD HITS (paths + text/attributes) ===")
    hits = find_nodes_by_keywords(root, keywords)
    for section, items in hits.items():
        print(f"\n--- {section} (showing up to {MAX_HITS_PER_KEYWORD}) ---")
        for i, it in enumerate(items[:MAX_HITS_PER_KEYWORD], start=1):
            print(f"{i:02d}. {it}")

    # 3) Special focus: Distance nodes (often pixel size)
    print("\n=== DISTANCE NODES (often pixel/voxel size) ===")
    show_distance_nodes(root, limit=50)


def find_text_by_tag(root: ET.Element, tag_name: str) -> list[str]:
    """Find all non-empty text values of nodes whose local tag == tag_name."""
    out = []
    for el in root.iter():
        if local_name(el.tag) == tag_name:
            txt = (el.text or "").strip()
            if txt:
                out.append(txt)
    return out


def find_nodes_by_keywords(root: ET.Element, keyword_map: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    For each section, find XML elements where:
    - tag name contains a keyword OR
    - attribute name contains a keyword OR
    - text contains a keyword (lightly; we keep it short)
    Returns printable strings including paths.
    """
    results = defaultdict(list)

    # DFS with stack to keep paths
    stack: list[str] = []

    def dfs(el: ET.Element):
        tag = local_name(el.tag)
        stack.append(tag)

        tag_l = tag.lower()
        text = (el.text or "").strip()
        text_l = text.lower()

        # collect attribute strings
        attr_items = []
        for k, v in el.attrib.items():
            attr_items.append(f"{k}={v}")
        attr_blob = " ".join(attr_items).lower()

        for section, keys in keyword_map.items():
            for kw in keys:
                kw_l = kw.lower()
                matched = False

                if kw_l in tag_l:
                    matched = True
                elif kw_l in attr_blob:
                    matched = True
                elif text and kw_l in text_l and len(text) <= 200:
                    matched = True

                if matched:
                    path = elem_path(stack)
                    descr = f"{path}"
                    if el.attrib:
                        descr += f" | attrs: {shorten(str(el.attrib))}"
                    if text:
                        descr += f" | text: {shorten(text)}"
                    results[section].append(descr)
                    break  # avoid duplicate hits for same element in same section

        for ch in list(el):
            dfs(ch)

        stack.pop()

    dfs(root)
    return results


def show_distance_nodes(root: ET.Element, limit: int = 50) -> None:
    """
    Print all elements with local tag 'Distance' (common in Zeiss scaling),
    showing attributes and child Value/Unit if present.
    """
    count = 0
    for el in root.iter():
        if local_name(el.tag).lower() == "distance":
            count += 1
            if count > limit:
                print(f"... (more than {limit} Distance nodes)")
                return

            axis = el.attrib.get("Id") or el.attrib.get("id") or el.attrib.get("Dimension") or ""
            value = None
            unit = None
            for ch in list(el):
                ch_tag = local_name(ch.tag).lower()
                if ch_tag == "value":
                    value = (ch.text or "").strip()
                elif ch_tag == "unit":
                    unit = (ch.text or "").strip()

            print(f"- Distance axis={axis!r}, value={value!r}, unit={unit!r}, attrs={el.attrib}")


if __name__ == "__main__":
    xml = get_czi_xml(CZI_PATH)
    print(f"[OK] Loaded XML from: {CZI_PATH}")
    print(f"[INFO] XML length: {len(xml)} characters")
    inspect(xml)

