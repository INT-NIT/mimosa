import re
from pathlib import Path
from pylibCZIrw import czi as czirw

class MimosaReader:
    def __init__(self, file_path):
        self.path = Path(file_path)
        self.metadata = None

    def __enter__(self):
        try:
            # On ouvre directement comme dans ton script
            with czirw.open_czi(str(self.path)) as doc:
                self.metadata = doc.metadata
            return self
        except Exception as e:
            print(f"Erreur d'ouverture {self.path.name}: {e}")
            return None

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Pas besoin de doc.close() ici car le 'with' au dessus l'a déjà fait
        pass

    # --- TES HELPERS ---
    def _find_key(self, data, target_key):
        if isinstance(data, dict):
            for k, v in data.items():
                if k.lower() == target_key.lower(): return v
                res = self._find_key(v, target_key)
                if res: return res
        elif isinstance(data, list):
            for item in data:
                res = self._find_key(item, target_key)
                if res: return res
        return None

    def _to_string(self, value):
        if value is None: return ""
        if isinstance(value, list) and value: return self._to_string(value[0])
        if isinstance(value, dict):
            return self._to_string(value.get("#text") or value.get("Value") or value.get("@Value"))
        return str(value).strip()

    # --- TES LOGIQUES D'EXTRACTION ---
    def get_subject(self):
        folder_name = self.path.parent.name
        parts = re.split(r'[-_]', folder_name)
        for p in parts:
            if p.isalpha() and len(p) > 2: return p.capitalize()
        return folder_name

    def get_session(self):
        raw_date = self._find_key(self.metadata, "AcquisitionDateAndTime") or self._find_key(self.metadata, "CreationDate")
        if raw_date:
            match = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", self._to_string(raw_date))
            if match: return "".join(match.groups())
        return "01"

    def get_acq_signature(self):
        # Microscope
        scope = "Unknown"
        devices = self._find_key(self.metadata, "Device")
        for d in (devices if isinstance(devices, list) else [devices] if devices else []):
            if self._to_string(d.get("@Id")) == "Microscope":
                scope = self._to_string(d.get("@Name"))
        # Scaling
        scaling = self._find_key(self.metadata, "Scaling")
        return f"{scope}_{str(scaling)[:30]}"

    def get_animal_info(self):
        return {
            "species": self._to_string(self._find_key(self.metadata, "Species") or "n/a"),
            "age": self._to_string(self._find_key(self.metadata, "Age") or "n/a"),
            "sex": "M" if "m" in self._to_string(self._find_key(self.metadata, "Sex")).lower() else "F"
        }
    def get_illumination_type(self) -> str:
        """
        Return illumination/contrast mode using ONLY:
        - IlluminationType
        - ContrastMethod
        """
        raw = self._find_key(self.metadata, "IlluminationType")
        if raw:
            val = self._to_string(raw)
            if val:
                return val

        raw = self._find_key(self.metadata, "ContrastMethod")
        if raw:
            val = self._to_string(raw)
            if val:
                return val

        return "Unknown"

    def get_summary(self):
        return {
            "sub": self.get_subject(),
            "ses": self.get_session(),
            "acq_sig": self.get_acq_signature(),
            "sample": "Cx" if any(x in self.path.name.lower() for x in ["cortex", "cx"]) else "Sam",
            "illumination": self.get_illumination_type(),  # <-- ajouté
            "animal": self.get_animal_info(),
            "full_meta": self.metadata
        }