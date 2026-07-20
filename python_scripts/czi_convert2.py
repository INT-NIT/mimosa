from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor

import nibabel as nib
import numpy as np
import tifffile as tf
from alive_progress import alive_bar
from pylibCZIrw import czi as pyczi

from BIDS import bids_manager as bm
from BIDS import bids_metadata as bmeta
from BIDS.czi_reader import MimosaReader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mimosa_downsample import (  # noqa: E402
    BLOCK_VALUES,
    READ_THREADS,
    downsample_scene,
)

# "decimate" keeps the historical desc so existing datasets and the slice
# preprocessor keep working unchanged.
DESC_BY_BLOCK_VALUE = {"decimate": "downsampled", "mean": "downsampledavg"}

# Scene/channel pairs exported concurrently. Each pair is independent: it reads
# its own ROI and writes its own files. Threads are enough because the two slow
# parts, CZI decoding and NumPy reduction, both release the GIL.
JOBS = 4


def _as_exponents(value):
    """Normalise one exponent or a collection of them into a sorted list."""
    if isinstance(value, (list, tuple, set)):
        return sorted({int(e) for e in value})
    return [int(value)]


def _as_res_labels(res_label, exponents):
    """Normalise res_label into {exponent: label}, defaulting to '<e>x'."""
    if res_label is None:
        return {e: f"{e}x" for e in exponents}
    if isinstance(res_label, dict):
        return {int(k): v for k, v in res_label.items()}
    if len(exponents) != 1:
        raise ValueError("a single res_label cannot cover several exponents")
    return {exponents[0]: res_label}


def _bids_basename(bids_info, stain, res_label, desc):
    """Build the BIDS basename, inserting res- and desc- when absent."""
    base = bm.build_bids_basename(bids_info=bids_info, stain=stain, suffix="FLUO")
    if "_res-" in base:
        return base
    return base.replace("_FLUO", f"_res-{res_label}_desc-{desc}_FLUO")


def _sidecar(reader, rect, stain, factor, scene_idx, shape, is_nifti,
             block_value, slice_position_map, thickness):
    """Build the JSON sidecar for one exported image, sform included."""
    meta = reader.get_converted_file_metadata(
        rect=rect,
        stain=stain,
        downsampling_factor=factor,
        is_nifti=is_nifti,
        scene_idx=scene_idx,
        exported_shape=(int(shape[0]), int(shape[1])),
    )
    meta["BlockValueMethod"] = block_value
    meta["BlockValueSource"] = "native CZI (no zoom)"

    if is_nifti and slice_position_map is not None:
        meta = bmeta.add_sform_to_json_metadata(
            meta=meta,
            slice_position_map=slice_position_map,
            original_thickness=thickness,
            block_value=block_value,
        )
    return meta


def _save_nifti(path, image, sform):
    """Write a 2D image as NIfTI with sform and qform set from one matrix."""
    img = nib.Nifti1Image(image, sform)
    img.set_sform(sform, code=1)
    img.set_qform(sform, code=1)
    img.header.set_xyzt_units("mm")
    nib.save(img, path)


def czi2bitmapHPC(
    pathin: str,
    czifilename: str,
    bids_root_path: str,
    bids_info: dict,
    downsampling_factor,
    output_format: str,
    res_label=None,
    reader=None,
    slice_position_map=None,
    original_thickness: float = 100,
    reorient: str = "none",
    block_value: str = "decimate",
    threads: int = READ_THREADS,
    jobs: int = JOBS,
):
    """Export one CZI to every requested resolution in a single native pass.

    downsampling_factor is an exponent or a list of them; passing several at
    once is nearly free because the native data is read only one time.
    block_value is "decimate" or "mean", and tags the output with its own BIDS
    desc- so both can coexist in one dataset. jobs exports that many
    scene/channel pairs at once, threads splits the reads inside each one.
    """
    if block_value not in BLOCK_VALUES:
        raise ValueError(f"block_value must be one of {BLOCK_VALUES}")

    output_format = output_format.lower().strip()
    if output_format not in ("tif", "nii", "both"):
        raise ValueError("output_format must be 'tif', 'nii' or 'both'")

    exponents = _as_exponents(downsampling_factor)
    res_labels = _as_res_labels(res_label, exponents)
    desc = DESC_BY_BLOCK_VALUE[block_value]
    write_tif = output_format in ("tif", "both")
    write_nii = output_format in ("nii", "both")

    with pyczi.open_czi(os.path.join(pathin, czifilename)) as czidoc:
        scenes = czidoc.scenes_bounding_rectangle
        nb_channels = MimosaReader.get_nb_channels(czidoc)

        folders = {
            e: bm.get_derivative_folder(bids_root_path, bids_info, res_labels[e])
            for e in exponents
        }
        for folder in folders.values():
            os.makedirs(folder, exist_ok=True)

        tasks = []
        for scene_idx in range(len(scenes)):
            slice_idx = reader.get_slice_index_for_scene(scene_idx)
            if slice_idx is None:
                print(f"  WARNING: no slice index for scene {scene_idx}, skipping")
                continue
            tasks += [(scene_idx, slice_idx, c) for c in range(nb_channels)]

        def export(task):
            """Export one scene/channel pair to every requested resolution."""
            scene_idx, slice_idx, channel_idx = task
            rect = scenes[scene_idx]
            stain = f"C{channel_idx}"
            # A copy per task: mutating the shared dict would let concurrent
            # scenes steal each other's chunk id.
            info = dict(bids_info, chunk=slice_idx)

            images = downsample_scene(
                czidoc=czidoc,
                roi=tuple(int(rect[i]) for i in range(4)),
                scene=scene_idx,
                channel=channel_idx,
                exponents=exponents,
                block_value=block_value,
                threads=threads,
            )

            written = []
            for exponent in exponents:
                image = images[exponent]
                factor = 2**exponent
                base = _bids_basename(info, stain, res_labels[exponent], desc)

                if write_tif:
                    path = os.path.join(folders[exponent], base + ".tif")
                    tf.imwrite(path, image, imagej=True)
                    bmeta.write_micr_sidecar_json(
                        path,
                        _sidecar(reader, rect, stain, factor, scene_idx,
                                 (image.shape[1], image.shape[0]), False,
                                 block_value, slice_position_map,
                                 original_thickness),
                    )
                    written.append(path)

                if write_nii:
                    path = os.path.join(folders[exponent], base + ".nii.gz")
                    arr = np.swapaxes(image, 0, 1)
                    meta = _sidecar(reader, rect, stain, factor, scene_idx,
                                    arr.shape[:2], True, block_value,
                                    slice_position_map, original_thickness)
                    _save_nifti(
                        path, arr,
                        np.asarray(meta.get("SFormMatrix", np.eye(4)), dtype=float),
                    )
                    bmeta.write_micr_sidecar_json(path, meta)
                    written.append(path)

            return written

        with alive_bar(len(tasks), force_tty=True, title=czifilename) as bar:
            def run(task):
                paths = export(task)
                bar()
                return paths

            if jobs > 1 and len(tasks) > 1:
                with ThreadPoolExecutor(max_workers=int(jobs)) as pool:
                    results = list(pool.map(run, tasks))
            else:
                results = [run(task) for task in tasks]

        for path in sorted(p for group in results for p in group):
            print(f"  -> {os.path.relpath(path, bids_root_path)}")

    return True
