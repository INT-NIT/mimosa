import re
from pathlib import Path
from pylibCZIrw import czi as czirw

class MimosaReader:
    # Variable de classe pour stocker la table
    correspondence_subject_sample = None
    
    @classmethod
    def load_correspondence_from_yaml(cls, cfg: dict) -> None:
        """loads subject/sample mapping from YAML — replaces CSV"""
        cls.correspondence_subject_sample = {}
        for entry in cfg.get("samples", {}).get("entries", []):
            path    = entry["path"].rstrip("/")   
            subject = entry["subject"]
            samples = entry.get("samples", [])
            
            if not samples:
                # fallback if sample isnt defined 
                cls.correspondence_subject_sample[path] = {
                    "subject": subject,
                    "sample":  "cx",  
                }
            else:
                cls.correspondence_subject_sample[path] = {
                    "subject":     subject,
                    "sample":      samples[0]["sample_id"].replace("sample-", ""),
                    "all_samples": [s["sample_id"].replace("sample-", "") for s in samples],
                    "files":       {        
                        f["filename"]: f.get("slices", [])
                        for s in samples
                        for f in s.get("files", [])
                    }
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
            raise RuntimeError(f"Cannot open CZI file {self.path.name}: {e}")

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
            for key in ("#text", "Value", "@Value", "Model", "@Name"):
                v = value.get(key)
                if v:
                    return self._to_string(v)
            return ""
        return str(value).strip()
    
    def get_subject(self):
        if self.correspondence_subject_sample:
            current = self.path.parent
            while current != current.parent:
                if str(current) in self.correspondence_subject_sample:
                    return self.correspondence_subject_sample[str(current)]['subject']
                current = current.parent
        
        folder_name = self.path.parent.name
        parts = re.split(r'[-_]', folder_name)
        for p in parts:
            if p.isalpha() and len(p) > 2: 
                return p.capitalize()
        return folder_name
    
    def get_sample(self):
        if self.correspondence_subject_sample:
            current = self.path.parent
            while current != current.parent:
                if str(current) in self.correspondence_subject_sample:
                    return self.correspondence_subject_sample[str(current)]['sample']
                current = current.parent

        return "Cx" if any(x in self.path.name.lower() for x in ["cortex", "cx"]) else "Unknown"

    def get_session(self) -> str:
        raw_date = (
            self._find_key(self.metadata, "CreationDate") 
        )

        if raw_date:
            raw_date = self._to_string(raw_date).strip()
            return raw_date

        return "n/a"
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
                vx = vx * 1e6
                vy = vy * 1e6
                
            return (vx, vy, "um")
        except Exception:
            return (1.0, 1.0, "um")
        
    
    def get_nb_channels(czidoc) -> int:
        md = czidoc.metadata
        n = int(md["ImageDocument"]["Metadata"]["Information"]["Image"]["SizeC"])
        if n == 0:
            while True:
                try:
                    _ = czidoc.read(roi=(0, 0, 10, 10), plane={"C": n})
                    n += 1
                except Exception:
                    break
        return n
    
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
    
    def get_acq_signature(self) -> str:
        """
        returns acquisition signature based on illumination type and pixel size.
        acq changes when illumination type or pixel size changes.
        """
        illumination = self.get_illumination_type()

        px_x, px_y, unit = self.get_pixel_size_um()

        res = f"{px_x:.2f}x{px_y:.2f}"

        return f"{illumination}-resolution-{res}"
    
    def get_manufacturer(self) -> str:
        """returns microscope name from metadata"""
        microscope = self._find_key(self.metadata, "Microscope")
        if isinstance(microscope, list):
            microscope = microscope[0]
        if microscope:
            name = self._to_string(microscope.get("@Name", ""))
            if name:
                return name
        return "Unknown"

    def get_chunk_transform_matrix(self, rect, pixel_size_um, downsampling_factor, slice_index=None):
        """
        Build BIDS ChunkTransformationMatrix.

        It maps local pixels of the saved image to physical coordinates
        in the slide/sample coordinate system.

        For a downsampled image:
            X_slide_um = out_px_um_x * x_downsampled_pixel + x0_um
            Y_slide_um = out_px_um_y * y_downsampled_pixel + y0_um

        rect.x and rect.y are assumed to be in original CZI pixel coordinates.
        PixelSizeUnits is micrometers.
        """

        px_um_x, px_um_y = pixel_size_um

        # Pixel size of the saved downsampled image
        out_px_um_x = float(px_um_x) * float(downsampling_factor)
        out_px_um_y = float(px_um_y) * float(downsampling_factor)

        try:
            x_px = float(rect.x)
            y_px = float(rect.y)
            w_px = float(rect.w)
            h_px = float(rect.h)
        except Exception:
            x_px = float(rect[0])
            y_px = float(rect[1])
            w_px = float(rect[2])
            h_px = float(rect[3])

        # Position of the scene origin in slide coordinates, in micrometers
        x0_um = x_px * float(px_um_x)
        y0_um = y_px * float(px_um_y)

        # Size of the saved downsampled image, in pixels
        w_downsampled = int(w_px / float(downsampling_factor))
        h_downsampled = int(h_px / float(downsampling_factor))

        # For now, keep ChunkTransformationMatrix as 2D.
        # SliceIndex stays as a separate metadata field.
        mat = [
            [out_px_um_x, 0.0, x0_um],
            [0.0, out_px_um_y, y0_um],
            [0.0, 0.0, 1.0],
        ]

        return mat, ["X", "Y"], [out_px_um_x, out_px_um_y], "um", w_downsampled, h_downsampled
    def get_slice_index_for_scene(self, scene_idx: int) -> int | None:
        """returns slice index for a given scene from YAML"""

        if self.correspondence_subject_sample:
            current = self.path.parent
            while current != current.parent:
                if str(current) in self.correspondence_subject_sample:
                    files  = self.correspondence_subject_sample[str(current)].get("files", {})
                    slices = files.get(self.path.name, [])
                    if scene_idx < len(slices):
                        return slices[scene_idx]
                    break
                current = current.parent
        return None

    def get_converted_file_metadata(
        self,
        rect,
        stain: str,
        downsampling_factor: int,
        is_nifti: bool,
        axis_swap: bool = False,
        scene_idx: int = 0
    ):
        slice_idx = self.get_slice_index_for_scene(scene_idx)

        manufacturer = self.get_manufacturer()
        px_um_x, px_um_y, unit = self.get_pixel_size_um()
        acq_sig = self.get_acq_signature()
        chunk_mat, axes, out_pix, out_unit, w_downsampled, h_downsampled = self.get_chunk_transform_matrix(
            rect, (px_um_x, px_um_y), downsampling_factor=downsampling_factor,slice_index=slice_idx
        )

        meta = {
            "Manufacturer": manufacturer,
            "PixelSize": out_pix,
            "PixelSizeUnits": out_unit,
            "SampleStaining": stain,
            "AcquisitionSignature": acq_sig,
            "AcquisitionDate": self.get_session(),
            "ChunkTransformationMatrix": chunk_mat,
            "ChunkTransformationMatrixAxis": axes,
            "Width": w_downsampled,
            "Height": h_downsampled,
            "DownsamplingFactor": downsampling_factor
        }

        if slice_idx is not None:
            meta["SliceIndex"] = slice_idx   

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
            "acq_time": self.get_session(),
            "acq_sig": self.get_acq_signature(),
            "sample": self.get_sample(),
            "illumination": self.get_illumination_type(),
            "full_meta": self.metadata
        }