from __future__ import annotations

import os
import numpy as np
import tifffile as tf
import nibabel as nib

from pylibCZIrw import czi as pyczi
from alive_progress import alive_bar

from BIDS import bids_manager as bm
from BIDS import bids_metadata as bmeta
from BIDS.czi_reader import MimosaReader


def czi2bitmapHPC(
    pathin: str,
    czifilename: str,
    bids_root_path: str,
    bids_info: dict,
    downsampling_factor: int,
    output_format: str,
    res_label: str ,
    reader=None,
    slice_position_map=None,
    original_thickness: float = 100,
    reorient: str = "none",
):
    effective_downsampling_factor = 2 ** downsampling_factor
    desc_label = "downsampled"
    czifile_path = os.path.join(pathin, czifilename)

    output_format = output_format.lower().strip()
    if output_format not in ("tif", "nii", "both"):
        raise ValueError("output_format must be 'tif', 'nii' or 'both'")

    write_tif = output_format in ("tif", "both")
    write_nii = output_format in ("nii", "both")

    with pyczi.open_czi(czifile_path) as czidoc:
        scenes = czidoc.scenes_bounding_rectangle
        nb_channels = MimosaReader.get_nb_channels(czidoc)

        raw_folder = bm.get_raw_micr_folder(bids_root_path, bids_info)
        deriv_folder = bm.get_derivative_folder(bids_root_path, bids_info, res_label) if write_nii else None
        zoom_factor = float(1.0 / effective_downsampling_factor)

        for scene_idx in range(len(scenes)):
            rect = scenes[scene_idx]
            roi = (rect[0], rect[1], rect[2], rect[3])

            slice_idx = reader.get_slice_index_for_scene(scene_idx)

            if slice_idx is None:
                print(f"  WARNING: no slice index for scene {scene_idx}, skipping")
                continue

            bids_info["section"] = slice_idx

            channel_images = {}
            for c in range(nb_channels):
                channel_images[c] = czidoc.read(roi=roi, plane={"C": c}, scene=scene_idx, zoom=zoom_factor)

            with alive_bar(nb_channels, force_tty=True, title=f"Scene {scene_idx}") as bar:
                for c in range(nb_channels):
                    channel_name = f"C{c}"
                    stain = channel_name
                    base = bm.build_bids_basename(
                        bids_info=bids_info,
                        stain=stain,
                        suffix="FLUO",
                    )

                    if "_res-" not in base:
                        base = base.replace("_FLUO", f"_res-{res_label}_desc-{desc_label}_FLUO")
                    if write_tif:
                        out_path = os.path.join(raw_folder, base + ".tif")
                        tf.imwrite(out_path, channel_images[c], imagej=True)
                        meta_tiff = reader.get_converted_file_metadata(
                            rect=rect,
                            stain=stain,
                            downsampling_factor=effective_downsampling_factor,
                            is_nifti=False,
                            axis_swap=False,
                            scene_idx=scene_idx
                        )
                        bmeta.write_micr_sidecar_json(out_path, meta_tiff)
                        print(f"  -> BIDS raw: {os.path.relpath(out_path, bids_root_path)}")

                    if write_nii:
                        out_path = os.path.join(deriv_folder, base + ".nii.gz")
                        arr = np.swapaxes(channel_images[c], 0, 1)

                        meta_nii = reader.get_converted_file_metadata(
                            rect=rect,
                            stain=stain,
                            downsampling_factor=effective_downsampling_factor,
                            is_nifti=True,
                            axis_swap=True,
                            scene_idx=scene_idx,

                        )

                        if slice_position_map is not None:
                            meta_nii = bmeta.add_sform_to_json_metadata(
                                meta=meta_nii,
                                slice_position_map=slice_position_map,
                                original_thickness=original_thickness,
                                reorient=reorient
                            )

                        sform = np.array(meta_nii.get("SFormMatrix", np.eye(4)), dtype=float)

                        img = nib.Nifti1Image(arr, sform)
                        img.set_sform(sform, code=1)
                        img.set_qform(sform, code=1)
                        img.header.set_xyzt_units("micron")

                        nib.save(img, out_path)

                        bmeta.write_micr_sidecar_json(out_path, meta_nii)
                        print(f"  -> derivatives: {os.path.relpath(out_path, bids_root_path)}")
                    bar()

    return True