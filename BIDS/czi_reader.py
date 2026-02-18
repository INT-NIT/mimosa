import re
import csv
from pathlib import Path
from pylibCZIrw import czi as czirw

class MimosaReader:
    # Variable de classe pour stocker la table
    correspondence_table = None
    
    @classmethod
    def load_correspondence_table(cls, csv_path):
        """Charge la table de correspondance une seule fois"""
        if cls.correspondence_table is None:
            cls.correspondence_table = {}
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cls.correspondence_table[row['Path']] = {
                        'subject': row['SubjectName'],
                        'sample': row['Sample']
                    }
    
    def __init__(self, file_path):
        self.path = Path(file_path)
        self.metadata = None
    
    def __enter__(self):
        try:
            with czirw.open_czi(str(self.path)) as doc:
                self.metadata = doc.metadata
            return self
        except Exception as e:
            print(f"Erreur d'ouverture {self.path.name}: {e}")
            return None
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def _find_key(self, data, target_key):
        if isinstance(data, dict):
            for k, v in data.items():
                if k.lower() == target_key.lower(): 
                    return v
                res = self._find_key(v, target_key)
                if res: 
                    return res
        elif isinstance(data, list):
            for item in data:
                res = self._find_key(item, target_key)
                if res: 
                    return res
        return None
    
    def _to_string(self, value):
        if value is None: 
            return ""
        if isinstance(value, list) and value: 
            return self._to_string(value[0])
        if isinstance(value, dict):
            return self._to_string(value.get("#text") or value.get("Value") or value.get("@Value"))
        return str(value).strip()
    
    def get_subject(self):
        if self.correspondence_table:
            current = self.path.parent
            while current != current.parent:
                if str(current) in self.correspondence_table:
                    return self.correspondence_table[str(current)]['subject']
                current = current.parent
        
        folder_name = self.path.parent.name
        parts = re.split(r'[-_]', folder_name)
        for p in parts:
            if p.isalpha() and len(p) > 2: 
                return p.capitalize()
        return folder_name
    
    def get_sample(self):
        if self.correspondence_table:
            current = self.path.parent
            while current != current.parent:
                if str(current) in self.correspondence_table:
                    return self.correspondence_table[str(current)]['sample']
                current = current.parent
        
        return "Cx" if any(x in self.path.name.lower() for x in ["cortex", "cx"]) else "Sam"
    
    def get_session(self):
        raw_date = self._find_key(self.metadata, "AcquisitionDateAndTime") or self._find_key(self.metadata, "CreationDate")
        if raw_date:
            match = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", self._to_string(raw_date))
            if match: 
                return "".join(match.groups())
        return "01"
    def get_pixel_size_um(self):
       
        scaling = self._find_key(self.metadata, "Scaling")
        if not isinstance(scaling, dict):
            return (1.0, 1.0, "um")

        try:
            items = scaling.get("Items", {})
            dist = items.get("Distance", [])

            vx = float(dist[0]["Value"])
            vy = float(dist[1]["Value"]) if len(dist) > 1 else vx
            if vx < 1e-3:
                vx *= 1e6
            if vy < 1e-3:
                vy *= 1e6
            return (vx, vy, "um")
        except Exception:
            return (1.0, 1.0, "um")
        
    def get_acq_signature(self):
        scope = "Unknown"
        devices = self._find_key(self.metadata, "Device")
        for d in (devices if isinstance(devices, list) else [devices] if devices else []):
            if self._to_string(d.get("@Id")) == "Microscope":
                scope = self._to_string(d.get("@Name"))
        scaling = self._find_key(self.metadata, "Scaling")
        return f"{scope}_{str(scaling)[:30]}"
    
    def get_animal_info(self):
        return {
            "species": self._to_string(self._find_key(self.metadata, "Species") or "n/a"),
            "age": self._to_string(self._find_key(self.metadata, "Age") or "n/a"),
            "sex": "M" if "m" in self._to_string(self._find_key(self.metadata, "Sex")).lower() else "F"
        }
    
    def get_illumination_type(self) -> str:
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
    
    def get_manufacturer(self) -> str:
        val = self._find_key(self.metadata, "Manufacturer")
        s = self._to_string(val)
        return s if s else "Unknown"
    
    def get_chunk_transform_matrix(self, rect, pixel_size_um, downsampling_factor=1):
        
        px_um_x, px_um_y = pixel_size_um

        out_px_um_x = px_um_x * downsampling_factor
        out_px_um_y = px_um_y * downsampling_factor

        try:
            x_px = float(rect.x)
            y_px = float(rect.y)
        except Exception:
            x_px = float(rect[0])
            y_px = float(rect[1])

        x_um = x_px * out_px_um_x
        y_um = y_px * out_px_um_y

        mat = [
            [1.0, 0.0, x_um],
            [0.0, 1.0, y_um],
            [0.0, 0.0, 1.0],
        ]
        return mat, ["X", "Y"], [out_px_um_x, out_px_um_y], "um"
    

    def get_microscopy_metadata_for_file(
        self,
        rect,
        stain: str,
        downsampling_factor: int,
        is_nifti: bool,
        axis_swap: bool = False,
    ):
        manufacturer = self.get_manufacturer()
        px_um_x, px_um_y, unit = self.get_pixel_size_um()

        chunk_mat, axes, out_pix, out_unit = self.get_chunk_transform_matrix(
            rect, (px_um_x, px_um_y), downsampling_factor=downsampling_factor
        )

        meta = {
            "Manufacturer": manufacturer,
            "PixelSize": out_pix,
            "PixelSizeUnits": out_unit,
            "SampleStaining": stain,
            "ChunkTransformationMatrix": chunk_mat,
            "ChunkTransformationMatrixAxis": axes,
            "DownsamplingFactor": downsampling_factor,
        }

        if is_nifti:
            meta["ConvertedTo"] = "NIfTI"
            if axis_swap:
                meta["AxisSwapApplied"] = "swapaxes(0,1)"
        else:
            meta["ConvertedTo"] = "TIFF"

        return meta 

    def get_summary(self):
        return {
            "sub": self.get_subject(),
            "ses": self.get_session(),
            "acq_sig": self.get_acq_signature(),
            "sample": self.get_sample(),
            "illumination": self.get_illumination_type(),
            "animal": self.get_animal_info(),
            "full_meta": self.metadata
        }