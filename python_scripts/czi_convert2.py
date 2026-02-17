from __future__ import annotations

import os
import numpy as np
import tifffile as tf
import nibabel as nib

from pylibCZIrw import czi as pyczi
from alive_progress import alive_bar

import bids_manager as bm


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


def czi2bitmapHPC(
    pathin: str,
    czifilename: str,
    bids_root_path: str,
    bids_info: dict,
    downsampling_factor: int,
    output_format: str,
    pipeline_name: str = "downsampled",
    summary_for_json: dict | None = None,
):
    
    if summary_for_json is None:
        summary_for_json = {}

    czifile_path = os.path.join(pathin, czifilename)

    bm.initialize_derivatives(bids_root_path, pipeline_name=pipeline_name)

    with pyczi.open_czi(czifile_path) as czidoc:
        scenes = czidoc.scenes_bounding_rectangle
        nb_channels = get_nb_channels(czidoc)

        zoom_factor = float(1.0 / downsampling_factor)

        # dossier cible selon format
        if output_format == "tiff":
            out_folder = bm.get_raw_micr_folder(bids_root_path, bids_info)
        elif output_format == "nii":
            out_folder = bm.get_derivative_folder(bids_root_path, pipeline_name, bids_info)
        else:
            raise ValueError("output_format must be 'tiff' or 'nii'")

        for scene_idx in range(len(scenes)):
            chunk = f"{scene_idx:02d}"
            rect = scenes[scene_idx]
            roi = (rect[0], rect[1], rect[2], rect[3])

            channel_images = {}
            for c in range(nb_channels):
                channel_images[c] = czidoc.read(
                    roi=roi, plane={"C": c}, scene=scene_idx, zoom=zoom_factor
                )

            with alive_bar(nb_channels, force_tty=True, title=f"Scene {scene_idx}") as bar:
                for c in range(nb_channels):
                    channel_name = f"C{c}"   
                    stain = channel_name

                    base = bm.build_bids_basename(
                        bids_info=bids_info,
                        stain=stain,
                        chunk=chunk,
                        suffix="FLUO",   
                    )

                    if output_format == "tiff":
                        out_path = os.path.join(out_folder, base + ".tiff")
                        tf.imwrite(out_path, channel_images[c], imagej=True)

                        md = bm.prepare_bids_metadata(summary_for_json, channel_name, c, scene_idx)
                        bm.write_bids_sidecar(out_path, md)

                        print(f"  -> BIDS: {os.path.relpath(out_path, bids_root_path)}")

                    else:  # nii => derivatives
                        out_path = os.path.join(out_folder, base + ".nii.gz")
                        arr = np.swapaxes(channel_images[c], 0, 1)
                        img = nib.Nifti1Image(arr, np.eye(4))
                        nib.save(img, out_path)

                        md = bm.prepare_derivative_metadata(summary_for_json, channel_name, c, downsampling_factor)
                        bm.write_bids_sidecar(out_path, md)

                        print(f"  -> derivatives: {os.path.relpath(out_path, bids_root_path)}")

                    bar()

    return True