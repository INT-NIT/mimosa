from pathlib import Path
from pylibCZIrw import czi as czirw
import json

def save_czi_metadata_json(czi_path: Path, out_json: Path) -> None:
    """Read all CZI metadata and save it to a JSON file."""
    with czirw.open_czi(str(czi_path)) as doc:
        meta = doc.metadata

    # Cette ligne fonctionne maintenant car out_json est un objet Path
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

def main() -> None:
    czi_path = Path("/envau/work/invibe/USERS/IBOS/data/Marmoset/lames/1-renamed/5-Sully-MIO21100401/originaux/MIO21100401_Cx_418_420.czi")
    # --- CORRECTION ICI ---
    # On transforme la string en objet Path
    out_json = Path("./metadata.json") 

    save_czi_metadata_json(czi_path, out_json)
    print(f"[OK] Saved metadata to: {out_json}")

if __name__ == "__main__":
    main()
    """
    Subject: Sully, Date: 2024-06-09T00:00:00, Sample: Cx
Placeholder: MIO21100401_Cx_418_420.czi
Rectangles de scènes {0: Rectangle(x=-165629, y=1512, w=76928, h=64662), 1: Rectangle(x=-90482, y=7654, w=76929, h=58510)}
    """