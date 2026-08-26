from __future__ import annotations

import os
import sys

import nibabel as nib
import numpy as np
import tifffile as tf
from alive_progress import alive_bar
from pylibCZIrw import czi as pyczi

from BIDS import bids_manager as bm
from BIDS import bids_metadata as bmeta
from BIDS.czi_reader import MimosaReader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from python_scripts.mimosa_downsample import downsample_scene_zoom  # noqa: E402

DESC = "downsampled"


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
             slice_position_map, thickness, reorient="none"):
    """Build the JSON sidecar for one exported image, sform included."""
    meta = reader.get_converted_file_metadata(
        rect=rect,
        stain=stain,
        downsampling_factor=factor,
        is_nifti=is_nifti,
        scene_idx=scene_idx,
        exported_shape=(int(shape[0]), int(shape[1])),
    )
    meta["DownsamplingSource"] = "CZI zoom (ZEN pyramid)"

    if is_nifti and slice_position_map is not None:
        meta = bmeta.add_sform_to_json_metadata(
            meta=meta,
            slice_position_map=slice_position_map,
            original_thickness=thickness,
            reorient=reorient,
        )
    return meta


def _save_nifti(path, image, sform):
    """Write a 2D image as NIfTI with sform and qform set from one matrix."""
    # One single convention: NIfTI slices in float32 (like the padded slices
    # and the 3D volume).
    img = nib.Nifti1Image(np.asarray(image, dtype=np.float32), sform)
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
):
    """Export one CZI to every requested resolution using the CZI zoom.

    downsampling_factor is an exponent or a list of them (factor = 2**exp).
    The reduction is done by the CZI `zoom` argument (ZEN pyramid).
    """
    output_format = output_format.lower().strip()
    if output_format not in ("tif", "nii", "both"):
        raise ValueError("output_format must be 'tif', 'nii' or 'both'")

    exponents = _as_exponents(downsampling_factor)
    res_labels = _as_res_labels(res_label, exponents)
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

        for scene_idx in range(len(scenes)):
            rect = scenes[scene_idx]
            roi = tuple(int(rect[i]) for i in range(4))

            slice_idx = reader.get_slice_index_for_scene(scene_idx)
            if slice_idx is None:
                print(f"  WARNING: no slice index for scene {scene_idx}, skipping")
                continue
            bids_info["chunk"] = slice_idx

            with alive_bar(nb_channels, force_tty=True,
                           title=f"Scene {scene_idx}") as bar:
                for channel_idx in range(nb_channels):
                    images = downsample_scene_zoom(
                        czidoc=czidoc, roi=roi, scene=scene_idx,
                        channel=channel_idx, exponents=exponents,
                    )
                    stain_label = f"C{channel_idx}"
                    staining_name = reader.get_channel_name(channel_idx)
                    for exponent in exponents:
                        image = images[exponent]
                        # Force ODD dimensions (add one background row/col if
                        # even). Odd + centered puts a pixel center exactly on 0
                        # for every slice AND every resolution, so raw, padded,
                        # volume align within a resolution AND res-4x/6x/8x align
                        # with each other (coarse pixels fall on fine pixels).
                        """
                        if image.shape[0] % 2 == 0:
                            image = np.pad(image, ((0, 1), (0, 0)))
                        if image.shape[1] % 2 == 0:
                            image = np.pad(image, ((0, 0), (0, 1)))
                        """
                        factor = 2**exponent
                        base = _bids_basename(
                            bids_info, stain_label, res_labels[exponent], DESC
                        )

                        if write_tif:
                            path = os.path.join(folders[exponent], base + ".tif")
                            tf.imwrite(path, image, imagej=True)
                            bmeta.write_micr_sidecar_json(
                                path,
                                _sidecar(reader, rect, staining_name, factor, scene_idx,
                                         (image.shape[1], image.shape[0]), False,
                                         slice_position_map,
                                         original_thickness, reorient),
                            )
                            print("  -> BIDS raw: "
                                  f"{os.path.relpath(path, bids_root_path)}")

                        if write_nii:
                            path = os.path.join(folders[exponent], base + ".nii.gz")
                            arr = np.swapaxes(image, 0, 1)
                            meta = _sidecar(reader, rect, staining_name, factor, scene_idx,
                                            arr.shape[:2], True,
                                            slice_position_map, original_thickness,
                                            reorient)
                            _save_nifti(
                                path, arr,
                                np.asarray(meta.get("SFormMatrix", np.eye(4)),
                                           dtype=float),
                            )
                            bmeta.write_micr_sidecar_json(path, meta)
                            print("  -> derivatives: "
                                  f"{os.path.relpath(path, bids_root_path)}")

                    del images
                    bar()

    return True
