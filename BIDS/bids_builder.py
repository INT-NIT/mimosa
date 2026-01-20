import json
import csv
from pathlib import Path

from czi_reader import MimosaReader


class MimosaBidsRootBuilder:
    """
    Génère les fichiers BIDS à la racine:
    - dataset_description.json (obligatoire)
    - participants.tsv (obligatoire)
    - participants.json (recommandé)
    """

    def __init__(self, source_dir: str, bids_root: str):
        self.source_dir = Path(source_dir)
        self.bids_root = Path(bids_root)
        self.bids_root.mkdir(parents=True, exist_ok=True)

        # sub_id (ex: "sub-01") -> {"species":..., "age":..., "sex":...}
        self.participants = {}

    # -------------------------
    # Normalisation (alias simple)
    # -------------------------
    def _norm_sub_id(self, sub: str) -> str:
        """
        Force le format 'sub-XX' si sub est numérique, sinon 'sub-<label>'.
        Ton MimosaReader peut renvoyer autre chose, donc on sécurise.
        """
        s = (sub or "").strip()
        s = s.replace("sub-", "").replace("sub_", "")
        if s.isdigit():
            return f"sub-{int(s):02d}"
        return f"sub-{s}" if s else "sub-01"

    def _norm_sex(self, sex: str) -> str:
        s = (sex or "").strip().lower()
        if s in {"m", "male", "man", "masculin", "masculine"}:
            return "M"
        if s in {"f", "female", "woman", "feminin", "feminine"}:
            return "F"
        if s in {"n/a", "na", "unknown", ""}:
            return "n/a"
        # parfois "M/F" ou autres trucs => on reste safe
        if "m" in s and "f" not in s:
            return "M"
        if "f" in s and "m" not in s:
            return "F"
        return "n/a"

    def _norm_species(self, species: str) -> str:
        s = (species or "").strip().lower()
        if not s or s in {"n/a", "na", "unknown"}:
            return "n/a"
        # mini alias utiles
        if s in {"mouse", "mice"}:
            return "mus musculus"
        if s == "human":
            return "homo sapiens"
        return s

    def _norm_age(self, age: str) -> str:
        s = (age or "").strip()
        if not s or s.lower() in {"n/a", "na", "unknown"}:
            return "n/a"
        # si c’est déjà un chiffre en texte => ok
        # sinon tu peux laisser tel quel (BIDS tolère string/number)
        return s

    # -------------------------
    # Collecte
    # -------------------------
    def scan(self):
        """
        Parcourt les .czi, utilise MimosaReader.get_summary()
        et construit self.participants
        """
        print(f"--- Scanning {self.source_dir} for .czi ---")
        for czi_path in self.source_dir.rglob("*.czi"):
            with MimosaReader(czi_path) as reader:
                if not reader or not reader.metadata:
                    continue

                summary = reader.get_summary()
                sub_id = self._norm_sub_id(summary.get("sub"))

                # init si nouveau
                if sub_id not in self.participants:
                    self.participants[sub_id] = {"species": "n/a", "age": "n/a", "sex": "n/a"}

                # on remplit seulement si on n'a pas encore l'info
                animal = summary.get("animal", {}) or {}

                if self.participants[sub_id]["species"] == "n/a":
                    self.participants[sub_id]["species"] = self._norm_species(animal.get("species"))
                if self.participants[sub_id]["age"] == "n/a":
                    self.participants[sub_id]["age"] = self._norm_age(animal.get("age"))
                if self.participants[sub_id]["sex"] == "n/a":
                    self.participants[sub_id]["sex"] = self._norm_sex(animal.get("sex"))

        print(f"--- Found {len(self.participants)} participants ---")

    # -------------------------
    # Écriture fichiers racine
    # -------------------------
    def write_dataset_description(self):
        file_path = self.bids_root / "dataset_description.json"
        content = {
            "Name": "Mimosa Axioscan Project",
            "BIDSVersion": "1.10.0",
            "DatasetType": "raw",
            "Authors": ["Your Name"],
            "GeneratedBy": [{"Name": "Mimosa BIDS Builder", "Version": "1.0.0"}],
        }
        file_path.write_text(json.dumps(content, indent=4, ensure_ascii=False), encoding="utf-8")

    def write_participants_tsv(self):
        file_path = self.bids_root / "participants.tsv"
        fieldnames = ["participant_id", "species", "age", "sex"]  # participant_id en 1er

        with file_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
            writer.writeheader()
            for sub_id in sorted(self.participants.keys()):
                row = {"participant_id": sub_id, **self.participants[sub_id]}
                writer.writerow(row)

    def write_participants_json(self):
        file_path = self.bids_root / "participants.json"
        sidecar = {
            "species": {"Description": "NCBI Taxonomy binomial name"},
            "age": {"Description": "Age of the participant", "Units": "n/a"},
            "sex": {
                "Description": "Biological sex of the participant",
                "Levels": {"M": "male", "F": "female"},
            },
        }
        file_path.write_text(json.dumps(sidecar, indent=4, ensure_ascii=False), encoding="utf-8")

    def build(self):
        self.scan()
        print("--- Writing BIDS root files ---")
        self.write_dataset_description()
        self.write_participants_tsv()
        self.write_participants_json()
        print(f"\n✅ SUCCESS: Root BIDS files written in: {self.bids_root}")


if __name__ == "__main__":
    ORIGINAL_DATA = "/envau/work/nit/users/boudlal.h/original-dataset"
    BIDS_DIR = "/envau/work/nit/users/boudlal.h/BIDS_dataset"

    MimosaBidsRootBuilder(ORIGINAL_DATA, BIDS_DIR).build()
