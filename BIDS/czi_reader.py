import re
from pathlib import Path
from pylibCZIrw import czi as czirw

class MimosaReader:
    # Variable de classe pour stocker la table
    correspondence_subject_sample = None
    
    @classmethod
    def load_correspondence_from_yaml(cls, cfg: dict) -> None:
        """
        Load subject/file/slice mapping from YAML.

        New YAML structure does not require sample_id.
        The real BIDS sample label, e.g. slide01, is assigned later in
        mimosa_hpc_converter2.py and stored in bids_info["sample"].

        Here we only need:
        - subject
        - filename -> slices
        - optionally filename -> derived_from / sample_type / participant_id
        """
        cls.correspondence_subject_sample = {}

        for entry in cfg.get("samples", {}).get("entries", []):
            path = entry["path"].rstrip("/")
            subject = entry.get("subject", "Unknown")
            samples = entry.get("samples", [])

            files_map = {}
            file_regions = {}
            file_sample_types = {}
            file_participants = {}

            for sample in samples:
                if not isinstance(sample, dict):
                    continue

                derived_from = sample.get("derived_from", "n/a")
                sample_type = sample.get("sample_type", "technical sample")
                participant_id = sample.get("participant_id", f"sub-{subject}")

                for f in sample.get("files") or []:
                    if not isinstance(f, dict):
                        continue

                    filename = f.get("filename")
                    if not filename:
                        continue

                    files_map[filename] = f.get("slices", [])
                    file_regions[filename] = derived_from
                    file_sample_types[filename] = sample_type
                    file_participants[filename] = participant_id

            cls.correspondence_subject_sample[path] = {
                "subject": subject,

                # Fallback only. The real sample used in filenames is set later
                # in bids_info["sample"] as slide01, slide02, etc.
                "sample": "slide",

                "files": files_map,
                "file_regions": file_regions,
                "file_sample_types": file_sample_types,
                "file_participants": file_participants,
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
    def get_channel_name(self, channel_idx: int) -> str:
        """
        Return the channel/stain name stored in the CZI metadata.

        Example:
            channel 0 -> DAPI
            channel 1 -> GFP

        Falls back to C0, C1, ... if no name is found.
        """

        try:
            image_info = (
                self.metadata["ImageDocument"]
                ["Metadata"]
                ["Information"]
                ["Image"]
            )

            channels = image_info.get("Dimensions", {}).get("Channels", {}).get(
                "Channel", []
            )

            if isinstance(channels, dict):
                channels = [channels]

            if channel_idx < len(channels):
                channel = channels[channel_idx]

                name = (
                    channel.get("@Name")
                    or channel.get("Name")
                    or channel.get("@Fluor")
                    or channel.get("Fluor")
                )

                if name:
                    return str(name).strip()

        except Exception:
            pass

        return f"C{channel_idx}"
    def get_chunk_transform_matrix(
        self,
        rect,
        pixel_size_um: tuple[float, float],
        downsampling_factor: float,
    ):
        """
        Build the 2D transformation of a CZI scene.

        The matrix maps pixels of the exported downsampled image to
        physical coordinates in the original CZI slide coordinate system.

        Coordinates and pixel sizes are expressed in micrometers.

        Parameters
        ----------
        rect
            Rectangle of the scene in native CZI pixel coordinates:
            x, y, width, height.

        pixel_size_um
            Native physical pixel size:
            (pixel_size_x_um, pixel_size_y_um).

        downsampling_factor
            Effective spatial downsampling factor applied to the image.

        Returns
        -------
        dict
            Native scene dimensions, physical extents, output pixel size
            and ChunkTransformationMatrix.
        """

        px_native_x_um = float(pixel_size_um[0])
        px_native_y_um = float(pixel_size_um[1])
        factor = float(downsampling_factor)

        if factor <= 0:
            raise ValueError(
                f"downsampling_factor must be positive, got {factor}"
            )

        try:
            x_native_px = float(rect.x)
            y_native_px = float(rect.y)
            width_native_px = int(rect.w)
            height_native_px = int(rect.h)
        except AttributeError:
            x_native_px = float(rect[0])
            y_native_px = float(rect[1])
            width_native_px = float(rect[2])
            height_native_px = float(rect[3])

        # Physical resolution of the exported downsampled image.
        pixel_size_x_ds_um = px_native_x_um * factor
        pixel_size_y_ds_um = px_native_y_um * factor

        # Physical position of the native scene origin in the CZI slide.
        scene_origin_x_um = x_native_px * px_native_x_um
        scene_origin_y_um = y_native_px * px_native_y_um

        # Native physical extent of the complete scene.
        width_native_um = width_native_px * px_native_x_um
        height_native_um = height_native_px * px_native_y_um

        chunk_transform = [
            [
                pixel_size_x_ds_um,
                0.0,
                scene_origin_x_um,
            ],
            [
                0.0,
                pixel_size_y_ds_um,
                scene_origin_y_um,
            ],
            [
                0.0,
                0.0,
                1.0,
            ],
        ]

        return {
            "ChunkTransformationMatrix": chunk_transform,
            "ChunkTransformationMatrixAxis": ["X", "Y"],
            "NativeWidthPixels": width_native_px,
            "NativeHeightPixels": height_native_px,
            "NativeWidthPhysical": width_native_um,
            "NativeHeightPhysical": height_native_um,
            "OutputPixelSize": [
                pixel_size_x_ds_um,
                pixel_size_y_ds_um,
            ],
            "OutputPixelSizeUnits": "um",
        }
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
        downsampling_factor: float,
        is_nifti: bool,
        scene_idx: int = 0,
        exported_shape: tuple[int, int] | None = None,
    ):
        """
        Build metadata for an exported TIFF or NIfTI image.

        exported_shape must describe the actual saved image grid:
            (size_x, size_y)

        For a NIfTI image, this should normally be:
            exported_shape = arr.shape[:2]

        It must not be estimated from the native CZI dimensions.
        """

        slice_index = self.get_slice_index_for_scene(scene_idx)

        manufacturer = self.get_manufacturer()
        px_native_x_um, px_native_y_um, native_unit = (
            self.get_pixel_size_um()
        )

        scene_geometry = self.get_chunk_transform_matrix(
            rect=rect,
            pixel_size_um=(
                px_native_x_um,
                px_native_y_um,
            ),
            downsampling_factor=downsampling_factor,
        )

        meta = {
            "Manufacturer": manufacturer,

            "NativePixelSize": [
                float(px_native_x_um),
                float(px_native_y_um),
            ],
            "NativePixelSizeUnits": native_unit,

            "PixelSize": scene_geometry["OutputPixelSize"],
            "PixelSizeUnits": scene_geometry[
                "OutputPixelSizeUnits"
            ],

            "NativeWidthPixels": scene_geometry[
                "NativeWidthPixels"
            ],
            "NativeHeightPixels": scene_geometry[
                "NativeHeightPixels"
            ],

            "WidthPhysical-Native": scene_geometry[
                "NativeWidthPhysical"
            ],
            "HeightPhysical-Native": scene_geometry[
                "NativeHeightPhysical"
            ],

            "SampleStaining": stain,
            "AcquisitionSignature": self.get_acq_signature(),
            "AcquisitionDate": self.get_session(),

            "ChunkTransformationMatrix": scene_geometry[
                "ChunkTransformationMatrix"
            ],
            "ChunkTransformationMatrixAxis": scene_geometry[
                "ChunkTransformationMatrixAxis"
            ],

            "DownsamplingFactor": float(downsampling_factor),
        }

        if exported_shape is not None:
            if len(exported_shape) != 2:
                raise ValueError(
                    "exported_shape must contain exactly "
                    "(size_x, size_y)"
                )

            size_x = int(exported_shape[0])
            size_y = int(exported_shape[1])

            if size_x <= 0 or size_y <= 0:
                raise ValueError(
                    f"Invalid exported shape: {exported_shape}"
                )

            meta["ExportedShape"] = [size_x, size_y]
            meta["WidthPixels-DS"] = size_x
            meta["HeightPixels-DS"] = size_y

        if slice_index is not None:
            meta["SliceIndex"] = int(slice_index)

        if is_nifti:
            meta["ConvertedTo"] = "NIfTI"
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