from pathlib import Path
from pylibCZIrw import czi as czirw
import json


def save_czi_metadata_json(czi_path: Path, out_json: Path) -> None:
    """Read all CZI metadata and save it to a JSON file."""
    with czirw.open_czi(str(czi_path)) as doc:
        meta = doc.metadata

    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


def main() -> None:
    czi_path = Path("/DATA/mimosa/original-dataset/1-Fenouil-MTO10092101/MTO10092101_Cx_200-208.czi")

    # output JSON next to the CZI (same folder), with "_metadata.json"
    out_json = czi_path.with_suffix("").with_name(czi_path.stem + "_metadata.json")

    save_czi_metadata_json(czi_path, out_json)
    print(f"[OK] Saved metadata to: {out_json}")


if __name__ == "__main__":
    main()
