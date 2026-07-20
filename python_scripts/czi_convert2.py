from __future__ import annotations

import os

import nibabel as nib
import numpy as np
import tifffile as tf
from alive_progress import alive_bar
from pylibCZIrw import czi as pyczi

from BIDS import bids_manager as bm
from BIDS import bids_metadata as bmeta
from BIDS.czi_reader import MimosaReader


def _read_decimated_native(
    czidoc,
    roi: tuple[int, int, int, int],
    scene_idx: int,
    channel_idx: int,
    factor: int,
    preferred_tile_size: int = 8192,
) -> np.ndarray:
    """Read a CZI scene at native resolution by tiles, then decimate it.

    Only existing native pixels are selected. No interpolation, averaging, or
    intensity recalculation is applied by this function.
    """
    if factor < 1:
        raise ValueError("factor must be greater than or equal to 1")

    x0, y0, width, height = (int(value) for value in roi)

    output_height = (height + factor - 1) // factor
    output_width = (width + factor - 1) // factor

    # Every tile starts on the same sampling grid as the complete ROI.
    # This avoids a shift at tile boundaries.
    tile_size = max(factor, (preferred_tile_size // factor) * factor)

    output = None

    for offset_y in range(0, height, tile_size):
        tile_height = min(tile_size, height - offset_y)

        for offset_x in range(0, width, tile_size):
            tile_width = min(tile_size, width - offset_x)

            tile_roi = (
                x0 + offset_x,
                y0 + offset_y,
                tile_width,
                tile_height,
            )

            native_tile = np.asarray(
                czidoc.read(
                    roi=tile_roi,
                    plane={"C": channel_idx},
                    scene=scene_idx,
                    zoom=1.0,
                )
            ).squeeze()

            if native_tile.ndim != 2:
                raise RuntimeError(
                    "Expected a 2D CZI tile, "
                    f"got shape {native_tile.shape} for scene {scene_idx}, "
                    f"channel {channel_idx}."
                )

            if output is None:
                output = np.empty(
                    (output_height, output_width),
                    dtype=native_tile.dtype,
                )

            sampled_tile = native_tile[::factor, ::factor]

            output_y = offset_y // factor
            output_x = offset_x // factor
            end_y = min(output_y + sampled_tile.shape[0], output_height)
            end_x = min(output_x + sampled_tile.shape[1], output_width)

            output[output_y:end_y, output_x:end_x] = sampled_tile[
                : end_y - output_y,
                : end_x - output_x,
            ]

    if output is None:
        raise RuntimeError(
            f"No pixels were read for scene {scene_idx}, channel {channel_idx}."
        )

    return output


def czi2bitmapHPC(
    pathin: str,
    czifilename: str,
    bids_root_path: str,
    bids_info: dict,
    downsampling_factor: int,
    output_format: str,
    res_label: str,
    reader=None,
    slice_position_map=None,
    original_thickness: float = 100,
    reorient: str = "none",
):
    effective_downsampling_factor = 2**downsampling_factor
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

        deriv_folder = bm.get_derivative_folder(
            bids_root_path,
            bids_info,
            res_label,
        )
        os.makedirs(deriv_folder, exist_ok=True)

        for scene_idx, rect in enumerate(scenes):
            roi = (
                int(rect[0]),
                int(rect[1]),
                int(rect[2]),
                int(rect[3]),
            )

            slice_idx = reader.get_slice_index_for_scene(scene_idx)
            if slice_idx is None:
                print(
                    f"  WARNING: no slice index for scene {scene_idx}, skipping"
                )
                continue

            bids_info["chunk"] = slice_idx

            with alive_bar(
                nb_channels,
                force_tty=True,
                title=f"Scene {scene_idx}",
            ) as bar:
                for channel_idx in range(nb_channels):
                    channel_image = _read_decimated_native(
                        czidoc=czidoc,
                        roi=roi,
                        scene_idx=scene_idx,
                        channel_idx=channel_idx,
                        factor=effective_downsampling_factor,
                    )

                    stain = f"C{channel_idx}"
                    base = bm.build_bids_basename(
                        bids_info=bids_info,
                        stain=stain,
                        suffix="FLUO",
                    )

                    if "_res-" not in base:
                        base = base.replace(
                            "_FLUO",
                            f"_res-{res_label}_desc-{desc_label}_FLUO",
                        )

                    if write_tif:
                        tif_path = os.path.join(deriv_folder, base + ".tif")
                        tf.imwrite(tif_path, channel_image, imagej=True)

                        meta_tiff = reader.get_converted_file_metadata(
                            rect=rect,
                            stain=stain,
                            downsampling_factor=effective_downsampling_factor,
                            is_nifti=False,
                            scene_idx=scene_idx,
                            exported_shape=(
                                int(channel_image.shape[1]),
                                int(channel_image.shape[0]),
                            ),
                        )
                        bmeta.write_micr_sidecar_json(tif_path, meta_tiff)
                        print(
                            "  -> BIDS raw: "
                            f"{os.path.relpath(tif_path, bids_root_path)}"
                        )

                    if write_nii:
                        nii_path = os.path.join(
                            deriv_folder,
                            base + ".nii.gz",
                        )
                        arr = np.swapaxes(channel_image, 0, 1)

                        meta_nii = reader.get_converted_file_metadata(
                            rect=rect,
                            stain=stain,
                            downsampling_factor=effective_downsampling_factor,
                            is_nifti=True,
                            scene_idx=scene_idx,
                            exported_shape=(
                                int(arr.shape[0]),
                                int(arr.shape[1]),
                            ),
                        )

                        if slice_position_map is not None:
                            meta_nii = bmeta.add_sform_to_json_metadata(
                                meta=meta_nii,
                                slice_position_map=slice_position_map,
                                original_thickness=original_thickness,
                            )

                        sform = np.asarray(
                            meta_nii.get("SFormMatrix", np.eye(4)),
                            dtype=float,
                        )

                        img = nib.Nifti1Image(arr, sform)
                        img.set_sform(sform, code=1)
                        img.set_qform(sform, code=1)
                        img.header.set_xyzt_units("mm")
                        nib.save(img, nii_path)

                        bmeta.write_micr_sidecar_json(nii_path, meta_nii)
                        print(
                            "  -> derivatives: "
                            f"{os.path.relpath(nii_path, bids_root_path)}"
                        )

                    del channel_image
                    bar()

    return True