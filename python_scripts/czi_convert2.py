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
):
   
    czifile_path = os.path.join(pathin, czifilename)

    output_format = output_format.lower().strip()
    if output_format not in ("tiff", "nii", "both"):
        raise ValueError("output_format must be 'tiff', 'nii' or 'both'")

    write_tiff = output_format in ("tiff", "both")
    write_nii = output_format in ("nii", "both")

    # derivatives seulement si on écrit du nii
    if output_format == "nii":
        bm.initialize_derivatives(bids_root_path, pipeline_name=pipeline_name)

    with pyczi.open_czi(czifile_path) as czidoc:
        scenes = czidoc.scenes_bounding_rectangle
        nb_channels = get_nb_channels(czidoc)

        raw_folder = bm.get_raw_micr_folder(bids_root_path, bids_info)
        deriv_folder = bm.get_derivative_folder(bids_root_path, pipeline_name, bids_info)

        zoom_factor = float(1.0 / downsampling_factor)

        for scene_idx in range(len(scenes)):
            chunk = f"{scene_idx:02d}"
            rect = scenes[scene_idx]
            roi = (rect[0], rect[1], rect[2], rect[3])

            # Lire chaque channel pour cette scene
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
                        chunk=chunk,
                        suffix="FLUO",
                    )

                    if write_tiff:
                        out_path = os.path.join(raw_folder, base + ".tif")
                        tf.imwrite(out_path, channel_images[c], imagej=True)
                        print(f"  -> BIDS raw: {os.path.relpath(out_path, bids_root_path)}")

                    if write_nii:
                        out_path = os.path.join(deriv_folder, base + ".nii.gz")
                        arr = np.swapaxes(channel_images[c], 0, 1)
                        img = nib.Nifti1Image(arr, np.eye(4))
                        nib.save(img, out_path)
                        print(f"  -> derivatives: {os.path.relpath(out_path, bids_root_path)}")

                    bar()

    return True