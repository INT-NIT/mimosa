# -*- coding: utf-8 -*-

import os
import sys
import math
import numpy as np
import tifffile
from pylibCZIrw import czi as pyczi


def get_dtype_from_czi(czidoc, channel=0):
    """
    Récupère le type de pixel du canal CZI et le convertit en dtype numpy.
    """

    pixel_type = czidoc.get_channel_pixel_type(channel)
    pixel_type = str(pixel_type).lower()

    if "gray8" in pixel_type or "uint8" in pixel_type:
        return np.uint8

    if "gray16" in pixel_type or "uint16" in pixel_type:
        return np.uint16

    if "gray32" in pixel_type or "float" in pixel_type:
        return np.float32

    print(f"Pixel type inconnu {pixel_type}, fallback uint16.")
    return np.uint16


def extract_2d_channel_from_read(arr):
    """
    czidoc.read() retourne souvent une image avec une dimension finale.
    Exemple : (Y, X, 1)
    On veut récupérer seulement (Y, X).
    """

    arr = np.asarray(arr)

    if arr.ndim == 2:
        return arr

    if arr.ndim == 3:
        return arr[..., 0]

    arr = np.squeeze(arr)

    if arr.ndim != 2:
        raise ValueError(f"Impossible de convertir le patch en 2D, shape={arr.shape}")

    return arr


def write_ome_tiff_single_channel(output_path, mosaic):
    """
    Écrit une mosaïque 2D en OME-TIFF avec axes YX.

    Cette version est volontairement simple pour être compatible avec FIJI/Bio-Formats.
    """

    tifffile.imwrite(
        output_path,
        mosaic,
        bigtiff=True,
        ome=True,
        metadata={
            "axes": "YX",
        },
    )


def convert_czi_total_bbox_to_ome_tiff(
    input_czi,
    output_dir,
    downsample_factor=1,
    patch_size=4096,
    channels=None,
    verbose_roi=False,
):
    """
    Convertit une lame CZI en OME-TIFF en utilisant le bounding box global.

    input_czi:
        chemin du fichier .czi

    output_dir:
        dossier de sortie

    downsample_factor:
        facteur de downsample.
        1 = pas de downsampling.
        8 = garde 1 pixel sur 8.

    patch_size:
        taille des patchs lus dans le CZI en pixels x1.
        Exemple : 4096 ou 8192.

    channels:
        liste des canaux à convertir.
        Exemple : [0] ou [0, 1].
        Si None, le script essaie de convertir tous les canaux trouvés.

    verbose_roi:
        True pour afficher chaque ROI lue.
        False pour éviter trop d'affichages.
    """

    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(input_czi))[0]

    with pyczi.open_czi(input_czi) as czidoc:
        total_bbox = czidoc.total_bounding_rectangle

        print("Total bounding rectangle:")
        print(total_bbox)
        print(f"x={total_bbox.x}, y={total_bbox.y}, w={total_bbox.w}, h={total_bbox.h}")

        if channels is None:
            channels = sorted(list(czidoc.pixel_types.keys()))

        print("Channels:", channels)

        out_width = math.ceil(total_bbox.w / downsample_factor)
        out_height = math.ceil(total_bbox.h / downsample_factor)

        print("Output size:")
        print("width =", out_width)
        print("height =", out_height)

        for channel in channels:
            dtype = get_dtype_from_czi(czidoc, channel)

            print("=" * 60)
            print(f"Converting channel C{channel}")
            print("dtype:", dtype)

            mosaic = np.zeros((out_height, out_width), dtype=dtype)

            for y0 in range(0, total_bbox.h, patch_size):
                for x0 in range(0, total_bbox.w, patch_size):
                    patch_w = min(patch_size, total_bbox.w - x0)
                    patch_h = min(patch_size, total_bbox.h - y0)

                    roi = (
                        total_bbox.x + x0,
                        total_bbox.y + y0,
                        patch_w,
                        patch_h,
                    )

                    if verbose_roi:
                        print(f"C{channel} ROI:", roi)

                    patch = czidoc.read(
                        roi=roi,
                        plane={"C": channel},
                    )

                    patch_2d = extract_2d_channel_from_read(patch)

                    if downsample_factor == 1:
                        patch_ds = patch_2d
                    else:
                        patch_ds = patch_2d[::downsample_factor, ::downsample_factor]

                    out_x0 = x0 // downsample_factor
                    out_y0 = y0 // downsample_factor

                    out_x1 = out_x0 + patch_ds.shape[1]
                    out_y1 = out_y0 + patch_ds.shape[0]

                    mosaic[out_y0:out_y1, out_x0:out_x1] = patch_ds

            output_path = os.path.join(
                output_dir,
                f"{base_name}_totalbbox_ds{downsample_factor}_C{channel}.ome.tiff",
            )

            write_ome_tiff_single_channel(output_path, mosaic)

            print("Written:", output_path)

            # Vérification rapide
            with tifffile.TiffFile(output_path) as tf:
                print("is_ome:", tf.is_ome)
                print("is_bigtiff:", tf.is_bigtiff)
                print("shape:", tf.series[0].shape)
                print("axes:", tf.series[0].axes)


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  python convert_czi_total_bbox_ome.py input.czi output_dir")
        print("")
        print("Options:")
        print("  --ds 1")
        print("  --patch 4096")
        print("  --channels 0,1")
        print("  --verbose-roi")
        print("")
        print("Exemples:")
        print("  python convert_czi_total_bbox_ome.py lame.czi ./out --ds 1 --channels 0")
        print("  python convert_czi_total_bbox_ome.py lame.czi ./out --ds 8 --channels 0,1")
        sys.exit(1)

    input_czi = sys.argv[1]
    output_dir = sys.argv[2]

    downsample_factor = 1
    patch_size = 4096
    channels = None
    verbose_roi = False

    args = sys.argv[3:]

    i = 0
    while i < len(args):
        if args[i] == "--ds":
            downsample_factor = int(args[i + 1])
            i += 2

        elif args[i] == "--patch":
            patch_size = int(args[i + 1])
            i += 2

        elif args[i] == "--channels":
            channels = [int(x) for x in args[i + 1].split(",")]
            i += 2

        elif args[i] == "--verbose-roi":
            verbose_roi = True
            i += 1

        else:
            raise ValueError(f"Argument inconnu : {args[i]}")

    convert_czi_total_bbox_to_ome_tiff(
        input_czi=input_czi,
        output_dir=output_dir,
        downsample_factor=downsample_factor,
        patch_size=patch_size,
        channels=channels,
        verbose_roi=verbose_roi,
    )


if __name__ == "__main__":
    main()