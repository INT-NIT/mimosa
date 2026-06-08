# -*- coding: utf-8 -*-

import os
import numpy as np
import tifffile
from pylibCZIrw import czi as pyczi


# ============================================================
# 1. PARAMÈTRES À MODIFIER ICI
# ============================================================

rootdir = "/chemin/vers/le/dossier_czi"
outdir = "/chemin/vers/le/dossier_sortie"
czifilename = "mon_fichier.czi"

# 1 = pas de downsampling
# 8 = garde 1 pixel sur 8
downsampling_factor = 8

# Comme dans ton notebook
patch_factor = 4
full_patch_w_h = 1536

# Canaux à convertir
# Exemple : (0,) pour seulement C0
# Exemple : (0, 1) pour C0 et C1
channels = (0, 1)


# ============================================================
# 2. FONCTION DE CONVERSION TOTAL BOUNDING BOX -> OME-TIFF
# ============================================================

def convert_czi_total_bbox_to_ome_tiff(
    pathin,
    czifilename,
    pathout,
    patch_factor=4,
    downsampling_factor=8,
    full_patch_w_h=1536,
    channels=(0, 1),
):
    """
    Convertit toute la lame CZI en OME-TIFF en utilisant total_bounding_rectangle.

    Différence avec ton notebook original :
        avant : scenes_bounding_rectangle[i]
        ici  : total_bounding_rectangle

    Donc le résultat est une grande mosaïque globale de toute la lame.

    Cette version écrit un fichier OME-TIFF par canal :
        fichier_totalbbox_ds8_C0.ome.tiff
        fichier_totalbbox_ds8_C1.ome.tiff
    """

    os.makedirs(pathout, exist_ok=True)

    czifile_scenes = os.path.join(pathin, czifilename)
    base_name = os.path.splitext(os.path.basename(czifilename))[0]

    print("Input CZI:", czifile_scenes)
    print("Output directory:", pathout)

    with pyczi.open_czi(czifile_scenes) as czidoc:

        bbox = czidoc.total_bounding_rectangle

        print("\nTotal bounding rectangle:")
        print(bbox)
        print("x =", bbox.x)
        print("y =", bbox.y)
        print("w =", bbox.w)
        print("h =", bbox.h)

        patch_width_full = patch_factor * full_patch_w_h
        patch_height_full = patch_factor * full_patch_w_h

        downsampled_patch_w = int(patch_width_full / downsampling_factor)
        downsampled_patch_h = int(patch_height_full / downsampling_factor)

        nb_patch_w = int(bbox.w / patch_width_full)
        nb_patch_h = int(bbox.h / patch_height_full)

        mosaic_image_width = round(float(bbox.w) / downsampling_factor + 0.5)
        mosaic_image_height = round(float(bbox.h) / downsampling_factor + 0.5)

        print("\nPatch information:")
        print("patch_width_full =", patch_width_full)
        print("patch_height_full =", patch_height_full)
        print("nb_patch_w =", nb_patch_w)
        print("nb_patch_h =", nb_patch_h)

        print("\nMosaic output size:")
        print("mosaic width =", mosaic_image_width)
        print("mosaic height =", mosaic_image_height)

        for channel in channels:

            print("\n" + "=" * 60)
            print("Converting channel C" + str(channel))
            print("=" * 60)

            mosaic_image = np.zeros(
                (int(mosaic_image_height), int(mosaic_image_width)),
                dtype=np.uint16,
            )

            for x in range(0, nb_patch_w + 1):
                for y in range(0, nb_patch_h + 1):

                    patch_width = patch_width_full
                    patch_height = patch_height_full

                    if y == nb_patch_h:
                        patch_height = bbox.h - (patch_height_full * y)

                    if x == nb_patch_w:
                        patch_width = bbox.w - (patch_width_full * x)

                    if patch_width <= 0 or patch_height <= 0:
                        continue

                    roi = (
                        bbox.x + patch_width_full * x,
                        bbox.y + patch_height_full * y,
                        patch_width,
                        patch_height,
                    )

                    print(
                        "C" + str(channel),
                        "x =", x,
                        "y =", y,
                        "roi =", roi,
                    )

                    patch = czidoc.read(
                        roi=roi,
                        plane={"C": channel},
                    )

                    patch = np.asarray(patch)

                    if patch.ndim == 3:
                        patch = patch[..., 0]
                    else:
                        patch = np.squeeze(patch)

                    if downsampling_factor == 1:
                        patch_res = patch
                    else:
                        patch_res = patch[::downsampling_factor, ::downsampling_factor]

                    out_y0 = y * downsampled_patch_h
                    out_x0 = x * downsampled_patch_w

                    out_y1 = out_y0 + patch_res.shape[0]
                    out_x1 = out_x0 + patch_res.shape[1]

                    mosaic_image[out_y0:out_y1, out_x0:out_x1] = patch_res

            output_name = (
                base_name
                + "_totalbbox_ds"
                + str(downsampling_factor)
                + "_C"
                + str(channel)
                + ".ome.tiff"
            )

            output_path = os.path.join(pathout, output_name)

            tifffile.imwrite(
                output_path,
                mosaic_image.astype(np.uint16),
                bigtiff=True,
                ome=True,
                metadata={
                    "axes": "YX",
                },
            )

            print("\nSaved:", output_path)

            # Vérification rapide
            with tifffile.TiffFile(output_path) as tf:
                print("is_ome:", tf.is_ome)
                print("is_bigtiff:", tf.is_bigtiff)
                print("shape:", tf.series[0].shape)
                print("axes:", tf.series[0].axes)


# ============================================================
# 3. LANCER LA CONVERSION
# ============================================================

if __name__ == "__main__":
    convert_czi_total_bbox_to_ome_tiff(
        pathin=rootdir,
        czifilename=czifilename,
        pathout=outdir,
        patch_factor=patch_factor,
        downsampling_factor=downsampling_factor,
        full_patch_w_h=full_patch_w_h,
        channels=channels,
    )