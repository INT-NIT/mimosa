# -*- coding: utf-8 -*-

import argparse
import json
import math
import os
import re
import sys
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import tifffile
from alive_progress import alive_bar
from pylibCZIrw import czi as pyczi

from BIDS import bids_metadata as bmeta
from BIDS import bids_manager as bm
from BIDS.czi_reader import MimosaReader

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from python_scripts.mimosa_downsample import READ_THREADS  # noqa: E402


# ============================================================
# Helpers
# ============================================================

def parse_channels(value: str) -> tuple[int, ...]:
    """
    Parse -channels 0,1 -> (0, 1)
    """
    return tuple(int(v.strip()) for v in value.split(",") if v.strip() != "")


def write_json_sidecar_for_ome_tiff(image_path: Path, meta: dict) -> None:
    """
    Write JSON sidecar for .ome.tiff.

    Example:
        image.ome.tiff -> image.json
    """
    image_path = Path(image_path)
    name = image_path.name

    if name.endswith(".ome.tiff"):
        json_path = image_path.with_name(name[:-9] + ".json")
    elif name.endswith(".ome.tif"):
        json_path = image_path.with_name(name[:-8] + ".json")
    elif name.endswith(".tiff"):
        json_path = image_path.with_name(name[:-5] + ".json")
    elif name.endswith(".tif"):
        json_path = image_path.with_name(name[:-4] + ".json")
    else:
        json_path = image_path.with_suffix(".json")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    print("sidecar created:", json_path)


def get_slice_indices_for_czi(cfg: dict, czi_filename: str) -> list[int]:
    """
    Get slice indices associated with one CZI file from metadata.yml.
    Fallback: extract from filename if possible.
    """
    slices = bmeta.get_slices_for_file(cfg, czi_filename)

    if slices:
        return [int(s) for s in slices]

    slices = bmeta.extract_slices_from_filename(czi_filename)
    return [int(s) for s in slices]


def get_subject_entries(cfg: dict):
    """
    Iterate over CZI files listed in metadata.yml.

    Returned item:
        input_dir
        czi_filename
        slices
        sample_info

    Subject/session are computed later using MimosaReader + BIDSSession,
    like in mimosa_hpc_converter2.py.
    """
    for entry in cfg.get("samples", {}).get("entries", []):
        input_dir = Path(entry["path"])

        for sample in entry.get("samples", []):
            files = sample.get("files", [])

            for file_entry in files:
                czi_filename = file_entry.get("filename")
                if not czi_filename:
                    continue

                slices = file_entry.get("slices")
                if not slices:
                    slices = get_slice_indices_for_czi(cfg, czi_filename)

                yield {
                    "input_dir": input_dir,
                    "czi_filename": czi_filename,
                    "slices": [int(s) for s in slices],
                    "sample_info": sample,
                }


def build_raw_bids_output_path(
    bids_root: Path,
    subject: str,
    session: str,
    sample_label: str,
    stain_label: str,
) -> Path:
    """
    Build raw BIDS output path without res, desc, or chunk.

    Example:
        sub-Una/ses-01/micr/
        sub-Una_ses-01_sample-slide01_stain-C0_FLUO.ome.tiff
    """
    out_dir = (
        Path(bids_root)
        / f"sub-{subject}"
        / f"ses-{session}"
        / "micr"
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    stain_clean = re.sub(r"[^a-zA-Z0-9]", "", stain_label)

    filename = (
        f"sub-{subject}"
        f"_ses-{session}"
        f"_sample-{sample_label}"
        f"_stain-{stain_clean}"
        f"_FLUO.ome.tiff"
    )

    return out_dir / filename


def rect_to_xywh(rect):
    """
    Return x, y, w, h from a pylibCZIrw rectangle object or tuple/list.
    """
    if hasattr(rect, "x") and hasattr(rect, "y") and hasattr(rect, "w") and hasattr(rect, "h"):
        return int(rect.x), int(rect.y), int(rect.w), int(rect.h)

    if isinstance(rect, (tuple, list)) and len(rect) >= 4:
        return int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])

    raise TypeError(f"Unsupported rectangle type: {type(rect)} value={rect}")


def iter_scene_rectangles(scenes):
    """
    Iterate over scene rectangles whether scenes_bounding_rectangle is a list or a dict.

    Some pylibCZIrw versions return:
        [rect0, rect1, ...]

    Others return:
        {0: rect0, 1: rect1, ...}
    """
    if isinstance(scenes, dict):
        for scene_idx, rect in sorted(scenes.items()):
            yield int(scene_idx), rect
    else:
        for scene_idx, rect in enumerate(scenes):
            yield int(scene_idx), rect


def build_scene_positions_metadata(
    scenes,
    total_bbox,
    downsampling_factor: int,
) -> list[dict]:
    """
    Build metadata describing original CZI scene bounding boxes and their
    positions in the global output mosaic.

    CZI coordinates are in original x1 CZI pixels.
    Output coordinates are in output mosaic pixels after downsampling.
    """
    total_x, total_y, _, _ = rect_to_xywh(total_bbox)

    scene_positions = []

    for scene_idx, rect in iter_scene_rectangles(scenes):
        x, y, w, h = rect_to_xywh(rect)

        output_x = int(round((x - total_x) / downsampling_factor))
        output_y = int(round((y - total_y) / downsampling_factor))
        output_w = int(math.ceil(w / downsampling_factor))
        output_h = int(math.ceil(h / downsampling_factor))

        scene_positions.append(
            {
                "SceneIndex": int(scene_idx),
                "CziBoundingBox": {
                    "X": x,
                    "Y": y,
                    "Width": w,
                    "Height": h,
                    "Units": "pixels",
                },
                "OutputBoundingBox": {
                    "X": output_x,
                    "Y": output_y,
                    "Width": output_w,
                    "Height": output_h,
                    "Units": "pixels",
                },
            }
        )

    return scene_positions


def make_sidecar_metadata(
    source_czi: Path,
    total_bbox,
    scenes,
    channel: int,
    downsampling_factor: int,
    width: int,
    height: int,
    slice_indices: list[int],
    sample_label: str,
    sample_info: dict,
) -> dict:
    """
    Metadata for raw BIDS OME-TIFF converted from a CZI using the global
    total_bounding_rectangle.

    This represents one whole slide, so SliceIndices is a list.
    """
    total_x, total_y, total_w, total_h = rect_to_xywh(total_bbox)

    scene_positions = build_scene_positions_metadata(
        scenes=scenes,
        total_bbox=total_bbox,
        downsampling_factor=downsampling_factor,
    )

    anatomical_region = sample_info.get("derived_from", "n/a")
    sample_type = sample_info.get("sample_type", "n/a")

    return {
        "SourceFile": source_czi.name,

        "ImageType": "OME-TIFF",
        "Axes": "YX",

        "Stain": f"C{channel}",

        "DownsamplingFactor": int(downsampling_factor),

        "Width": int(width), # final width of the final image OME-TIFF after downsampling 
        "Height": int(height),

        "SampleLabel": sample_label,
        "SliceIndices": [int(s) for s in slice_indices],

        "SampleType": sample_type,
        "AnatomicalRegion": anatomical_region,

        "TotalBoundingBox": { # cadre global de toute la lame avant downsampling 
            "X": total_x,
            "Y": total_y,
            "Width": total_w,
            "Height": total_h,
            "Units": "pixels",
            "Description": (
                "Global CZI bounding box used to build the output mosaic. "
                "Coordinates are in the original x1 CZI pixel reference."
            ),
        },

        "Scenes": scene_positions,

        "ScenePositionDescription": (
            "CziBoundingBox gives each original scene position in the CZI x1 pixel "
            "reference. OutputBoundingBox gives the corresponding position in the "
            "downsampled output mosaic."
        ),
    }


def get_next_slide_label(
    samples_rows: list[dict],
    participant_id: str,
) -> str:
    """
    Build sample labels slide01, slide02, slide03...
    based on already created sample rows for this participant.
    """
    count = 0

    for row in samples_rows:
        if (
            row.get("participant_id") == participant_id
            and str(row.get("sample_id", "")).startswith("sample-slide")
        ):
            count += 1

    return f"slide{count + 1:02d}"


def downsample_patch_nearest(patch: np.ndarray, factor: int) -> np.ndarray:
    """
    Downsample patch by keeping one pixel every factor pixels.

    Same simple logic as:
        patch[::factor, ::factor]
    """
    return patch[::factor, ::factor]

def inject_scene_positions_into_ome_xml(
    existing_xml: str,
    scenes,
    total_bbox,
    downsampling_factor: int,
) -> str:
    """
    Inject scene positions as a MapAnnotation into the OME-XML generated by tifffile.
    Does NOT touch SizeX, SizeY, or TiffData — only adds a StructuredAnnotations block.
    """
    ome_ns = "http://www.openmicroscopy.org/Schemas/OME/2016-06"
    ET.register_namespace("", ome_ns)
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")

    root = ET.fromstring(existing_xml)

    # Find or create StructuredAnnotations
    sa = root.find(f"{{{ome_ns}}}StructuredAnnotations")
    if sa is None:
        sa = ET.SubElement(root, f"{{{ome_ns}}}StructuredAnnotations")

    annotation_id = "Annotation:ScenePositions"

    # Add AnnotationRef to Image:0
    image = root.find(f"{{{ome_ns}}}Image")
    if image is not None:
        ET.SubElement(image, f"{{{ome_ns}}}AnnotationRef", {"ID": annotation_id})

    # Build MapAnnotation
    map_annotation = ET.SubElement(
        sa,
        f"{{{ome_ns}}}MapAnnotation",
        {"ID": annotation_id, "Namespace": "MIMOSA:ScenePositions"},
    )
    value = ET.SubElement(map_annotation, f"{{{ome_ns}}}Value")

    def add_kv(key: str, val) -> None:
        m = ET.SubElement(value, f"{{{ome_ns}}}M", {"K": str(key)})
        m.text = str(val)

    total_x, total_y, total_w, total_h = rect_to_xywh(total_bbox)
    add_kv("TotalBoundingBox.X", total_x)
    add_kv("TotalBoundingBox.Y", total_y)
    add_kv("TotalBoundingBox.Width", total_w)
    add_kv("TotalBoundingBox.Height", total_h)
    add_kv("TotalBoundingBox.Units", "pixels")
    add_kv("DownsamplingFactor", downsampling_factor)

    scene_positions = build_scene_positions_metadata(
        scenes=scenes,
        total_bbox=total_bbox,
        downsampling_factor=downsampling_factor,
    )
    add_kv("SceneCount", len(scene_positions))

    for scene in scene_positions:
        idx = int(scene["SceneIndex"])
        czi_box = scene["CziBoundingBox"]
        out_box = scene["OutputBoundingBox"]
        add_kv(f"Scene:{idx}.CziBoundingBox.X", czi_box["X"])
        add_kv(f"Scene:{idx}.CziBoundingBox.Y", czi_box["Y"])
        add_kv(f"Scene:{idx}.CziBoundingBox.Width", czi_box["Width"])
        add_kv(f"Scene:{idx}.CziBoundingBox.Height", czi_box["Height"])
        add_kv(f"Scene:{idx}.CziBoundingBox.Units", "pixels")
        add_kv(f"Scene:{idx}.OutputBoundingBox.X", out_box["X"])
        add_kv(f"Scene:{idx}.OutputBoundingBox.Y", out_box["Y"])
        add_kv(f"Scene:{idx}.OutputBoundingBox.Width", out_box["Width"])
        add_kv(f"Scene:{idx}.OutputBoundingBox.Height", out_box["Height"])
        add_kv(f"Scene:{idx}.OutputBoundingBox.Units", "pixels")

    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes.decode("utf-8")


# Conversion
def convert_one_czi_total_bbox_to_raw_bids_ome_tiff(
    input_czi: Path,
    bids_root: Path,
    subject: str,
    session: str,
    slice_indices: list[int],
    sample_info: dict,
    sample_label: str,
    downsampling_factor: int,
    channels: tuple[int, ...],
    patch_size: int = 6144,
    threads: int = READ_THREADS,
    compression: str = "zlib",
    quality: float = 0.5,
):
    import tempfile
    import os

    input_czi = Path(input_czi)
    bids_root = Path(bids_root)

    print("\n" + "=" * 80)
    print("Input CZI:", input_czi)
    print("Subject:", subject)
    print("Session:", session)
    print("Sample label:", sample_label)
    print("SliceIndices:", slice_indices)
    print("Channels:", channels)
    print("Downsampling:", downsampling_factor)
    print("Patch size:", patch_size)
    print("=" * 80)

    with pyczi.open_czi(str(input_czi)) as czidoc:
        bbox = czidoc.total_bounding_rectangle
        scenes = czidoc.scenes_bounding_rectangle

        bbox_x, bbox_y, bbox_w, bbox_h = rect_to_xywh(bbox)

        print("\nTotal bounding rectangle:")
        print("x =", bbox_x)
        print("y =", bbox_y)
        print("w =", bbox_w)
        print("h =", bbox_h)

        patch_width_full = int(patch_size)
        patch_height_full = int(patch_size)

        nb_patch_w = int(math.ceil(bbox_w / patch_width_full))
        nb_patch_h = int(math.ceil(bbox_h / patch_height_full))

        mosaic_image_width = int(math.ceil(bbox_w / downsampling_factor))
        mosaic_image_height = int(math.ceil(bbox_h / downsampling_factor))

        print("\nPatch information:")
        print("patch_width_full =", patch_width_full)
        print("patch_height_full =", patch_height_full)
        print("nb_patch_w =", nb_patch_w)
        print("nb_patch_h =", nb_patch_h)

        print("\nMosaic output size:")
        print("mosaic width =", mosaic_image_width)
        print("mosaic height =", mosaic_image_height)

        total_patches = nb_patch_w * nb_patch_h

        for channel in channels:
            stain_label = f"C{channel}"

            print("\n" + "-" * 80)
            print(f"Converting sample={sample_label}, SliceIndices={slice_indices}, stain={stain_label}")
            print("-" * 80)

            mosaic_image = np.zeros(
                (int(mosaic_image_height), int(mosaic_image_width)),
                dtype=np.uint16,
            )

            def fill_patch(idx):
                """Read one patch, downsample it, write it into the mosaic.

                Patches cover disjoint mosaic regions, so several run in
                parallel with no locking: each writes only its own slice.
                """
                x_idx, y_idx = idx
                src_x0 = x_idx * patch_width_full
                src_y0 = y_idx * patch_height_full

                patch_width = min(patch_width_full, bbox_w - src_x0)
                patch_height = min(patch_height_full, bbox_h - src_y0)
                if patch_width <= 0 or patch_height <= 0:
                    return

                roi = (bbox_x + src_x0, bbox_y + src_y0, patch_width, patch_height)
                patch = np.asarray(czidoc.read(roi=roi, plane={"C": channel}))
                patch = patch[..., 0] if patch.ndim == 3 else np.squeeze(patch)

                patch_res = downsample_patch_nearest(patch=patch, factor=downsampling_factor)

                out_x0 = int(round(src_x0 / downsampling_factor))
                out_y0 = int(round(src_y0 / downsampling_factor))
                out_x1 = min(out_x0 + patch_res.shape[1], mosaic_image_width)
                out_y1 = min(out_y0 + patch_res.shape[0], mosaic_image_height)

                mosaic_image[out_y0:out_y1, out_x0:out_x1] = (
                    patch_res[: out_y1 - out_y0, : out_x1 - out_x0]
                )

            patch_indices = [
                (x_idx, y_idx)
                for x_idx in range(nb_patch_w)
                for y_idx in range(nb_patch_h)
            ]

            with alive_bar(
                total_patches,
                force_tty=True,
                title=f"{sample_label} {stain_label} ds{downsampling_factor}x",
            ) as bar:
                def run(idx):
                    fill_patch(idx)
                    bar()

                if threads > 1 and total_patches > 1:
                    with ThreadPoolExecutor(max_workers=int(threads)) as pool:
                        list(pool.map(run, patch_indices))
                else:
                    for idx in patch_indices:
                        run(idx)

            output_path = build_raw_bids_output_path(
                bids_root=bids_root,
                subject=subject,
                session=session,
                sample_label=sample_label,
                stain_label=stain_label,
            )

            # Step 1 : écrire un fichier temporaire pour récupérer l'XML correct généré par tifffile
            with tempfile.NamedTemporaryFile(suffix=".tiff", delete=False) as tmp:
                tmp_path = tmp.name

            tifffile.imwrite(
                tmp_path,
                mosaic_image.astype(np.uint16),
                photometric="minisblack",
                ome=True,                        
                metadata={"axes": "YX"},
            )

            with tifffile.TiffFile(tmp_path) as tf:
                xml_str = tf.ome_metadata

            os.unlink(tmp_path)
            if xml_str is None:
                raise RuntimeError(f"tifffile did not generate OME-XML for {output_path.name}")
            # Step 2 : injecter les positions de scènes dans l'XML correct
            enriched_xml = inject_scene_positions_into_ome_xml(
                existing_xml=xml_str,
                scenes=scenes,
                total_bbox=bbox,
                downsampling_factor=downsampling_factor,
            )

            # Step 3 : écrire le vrai fichier BigTIFF avec l'XML enrichi.
            # zlib is lossless but weak on fluorescence data (~10%). jpegxr and
            # jpeg2000 are lossy: they shrink the file a lot (like the CZI does)
            # at the cost of slightly altered pixel values. Lossy is fine for a
            # visual overview but must not be used for quantification.
            write_kwargs = dict(
                photometric="minisblack",
                description=enriched_xml,
                metadata=None,
                compression=compression,
            )
            if compression in ("jpegxr", "jpeg2000"):
                write_kwargs["compressionargs"] = {"level": float(quality)}

            with tifffile.TiffWriter(str(output_path), bigtiff=True) as tif:
                tif.write(mosaic_image.astype(np.uint16), **write_kwargs)

            print("Written:", output_path)

            meta = make_sidecar_metadata(
                source_czi=input_czi,
                total_bbox=bbox,
                scenes=scenes,
                channel=channel,
                downsampling_factor=downsampling_factor,
                width=mosaic_image.shape[1],
                height=mosaic_image.shape[0],
                slice_indices=slice_indices,
                sample_label=sample_label,
                sample_info=sample_info,
            )

            # Record the compression so a reader knows whether the pixel values
            # are exact (lossless) or slightly altered (lossy overview).
            meta["Compression"] = compression
            meta["Lossy"] = compression in ("jpegxr", "jpeg2000")
            if meta["Lossy"]:
                meta["CompressionQuality"] = float(quality)

            write_json_sidecar_for_ome_tiff(output_path, meta)

            with tifffile.TiffFile(str(output_path)) as tf:
                print("is_ome:", tf.is_ome)
                print("is_bigtiff:", tf.is_bigtiff)
                print("shape:", tf.series[0].shape)
                print("axes:", tf.series[0].axes)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert CZI files listed in metadata.yml to raw BIDS OME-TIFF "
            "using total_bounding_rectangle."
        )
    )

    parser.add_argument(
        "-y",
        required=True,
        help="Path to metadata.yml",
    )

    parser.add_argument(
        "-bids_root",
        required=True,
        help="Output BIDS root.",
    )

    parser.add_argument(
        "-df",
        type=int,
        choices=[1 , 2, 4, 6, 8],
        default=8,
        help="Downsampling factor. Allowed values: 2, 4, 6, 8.",
    )

    parser.add_argument(
        "-channels",
        default="0,1",
        help="Channels to convert, for example: 0 or 0,1",
    )

    parser.add_argument(
        "-patch_size",
        type=int,
        default=6144,
        help="Patch size in x1 pixels used to read the CZI by blocks.",
    )

    parser.add_argument(
        "-threads",
        type=int,
        default=READ_THREADS,
        help=(
            "Patches read and downsampled concurrently. They cover disjoint "
            "mosaic regions, so this only speeds things up, the output is "
            "identical. Set it near your core count; use 1 to disable."
        ),
    )

    parser.add_argument(
        "-compression",
        type=str,
        default="zlib",
        choices=("zlib", "jpegxr", "jpeg2000"),
        help=(
            "How to compress the OME-TIFF. 'zlib' is lossless but weak on "
            "fluorescence (~10%%), so the file stays large. 'jpegxr' and "
            "'jpeg2000' are lossy: much smaller (like the CZI), at the cost of "
            "slightly altered pixel values. Use lossy only for a visual "
            "overview, never for quantification."
        ),
    )

    parser.add_argument(
        "-quality",
        type=float,
        default=0.5,
        help=(
            "Quality level for lossy compression. ONLY affects jpegxr and "
            "jpeg2000; it does NOTHING for zlib, which is lossless and keeps "
            "every value exactly. Lower means smaller and more altered. 0.5 is "
            "a good mild overview setting, about 6x smaller than lossless."
        ),
    )

    args = parser.parse_args()

    metadata_path = Path(args.y)
    channels = parse_channels(args.channels)

    bids_root = Path(
        bm.initialize_dataset(
            bids_root_path=args.bids_root,
            yaml_path=str(metadata_path),
            output_format="ome",
        )
    )

    cfg = bmeta.update_yaml_with_slices(metadata_path)
    MimosaReader.load_correspondence_from_yaml(cfg)   
    session = bm.BIDSSession(str(bids_root))

    sessions_by_sub = {}
    samples_rows = []

    for item in get_subject_entries(cfg):
        input_czi = item["input_dir"] / item["czi_filename"]

        if not input_czi.exists():
            print("WARNING: CZI not found:", input_czi)
            continue

        if not item["slices"]:
            print("WARNING: no slices for:", input_czi.name)
            continue

        czi_id = input_czi.stem

        try:
            with MimosaReader(str(input_czi)) as reader:
                summary = reader.get_summary()

            print("\n>>> Processing:", input_czi.name)
            print(
                f"    Subject: {summary['sub']}, "
                f"Date: {summary['acq_time']}, "
                f"Sample: {summary['sample']}"
            )

            bids_info = session.get_bids_info(
                summary_meta=summary,
                czi_id=czi_id,
                section_idx=None,
            )

            subject = bids_info["sub"]
            session_id = bids_info["ses"]

            print("BIDS info:", bids_info)

            bm.create_sourcedata_links(
                str(input_czi),
                subject,
                str(bids_root),
            )

            participant_id = item["sample_info"].get(
                "participant_id",
                f"sub-{subject}",
            )

            sample_label = get_next_slide_label(
                samples_rows=samples_rows,
                participant_id=participant_id,
            )

            sample_id = f"sample-{sample_label}"

            samples_rows.append(
                {
                    "sample_id": sample_id,
                    "participant_id": participant_id,
                    "sample_type": item["sample_info"].get(
                        "sample_type",
                        "technical sample",
                    ),
                    "derived_from": item["sample_info"].get(
                        "derived_from",
                        "n/a",
                    ),
                    "source_filename": input_czi.name,
                }
            )

            ses_key = f"ses-{session_id}"

            sessions_by_sub.setdefault(subject, {})
            sessions_by_sub[subject][ses_key] = bids_info["acq_time"]

            convert_one_czi_total_bbox_to_raw_bids_ome_tiff(
                input_czi=input_czi,
                bids_root=bids_root,
                subject=subject,
                session=session_id,
                slice_indices=item["slices"],
                sample_info=item["sample_info"],
                sample_label=sample_label,
                downsampling_factor=args.df,
                channels=channels,
                patch_size=args.patch_size,
                threads=args.threads,
                compression=args.compression,
                quality=args.quality,
            )

        except Exception as exc:
            print(f"ERROR processing {input_czi.name}: {exc}")
            continue

    for sub, session_dict in sessions_by_sub.items():
        rows = [
            {
                "session_id": ses_id,
                "acq_time": session_dict[ses_id],
            }
            for ses_id in sorted(session_dict.keys())
        ]

        bmeta.write_subject_sessions_tsv(
            str(bids_root),
            sub,
            rows,
        )

    if samples_rows:
        bmeta.write_samples_tsv(bids_root, samples_rows)

    print("\n[SUCCESS] Total bounding-box raw OME-TIFF conversion done.")


if __name__ == "__main__":
    main()


"""
Example:

python mimosa_czi2ometiff_converter.py \
  -y metadata.yml \
  -bids_root /envau/work/nit/users/boudlal.h/BIDS-test \
  -ds 8 \
  -channels 0
"""