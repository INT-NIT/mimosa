# -*- coding: utf-8 -*-

import os
import numpy as np
from PIL import Image
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

# Comme dans le notebook
patch_factor = 4
full_patch_w_h = 1536

# Canaux à convertir
# Exemple : (0,) pour seulement C0
# Exemple : (0, 1) pour C0 et C1
channels = (0, 1)


# ============================================================
# 2. FONCTION DE CONVERSION TOTAL BOUNDING BOX
# ============================================================

def convert_czi_total_bbox_to_tiff(
    pathin,
    czifilename,
    pathout,
    patch_factor=4,
    downsampling_factor=8,
    full_patch_w_h=1536,
    channels=(0, 1),
):
    """
    Convertit toute la lame CZI en utilisant total_bounding_rectangle.

    C'est la même logique que le notebook original, mais au lieu de faire :

        scenes_bounding_rectangle = czidoc.scenes_bounding_rectangle

    on fait :

        bbox = czidoc.total_bounding_rectangle

    Donc le résultat est une grande mosaïque globale de toute la lame.
    """

    os.makedirs(pathout, exist_ok=True)

    czifile_scenes = os.path.join(pathin, czifilename)
    base_name = os.path.splitext(os.path.basename(czifilename))[0]

    print("Input CZI:", czifile_scenes)
    print("Output directory:", pathout)

    with pyczi.open_czi(czifile_scenes) as czidoc:

        # Ici on prend toute la lame, pas les scènes séparées
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
                dtype="uint16",
            )

            for x in range(0, nb_patch_w + 1):
                for y in range(0, nb_patch_h + 1):

                    patch_width = patch_width_full
                    patch_height = patch_height_full

                    if y == nb_patch_h:
                        patch_height = bbox.h - (patch_height_full * y)

                    if x == nb_patch_w:
                        patch_width = bbox.w - (patch_width_full * x)

                    # Si on tombe exactement sur le bord, patch_width ou patch_height peut être 0
                    if patch_width <= 0 or patch_height <= 0:
                        continue

                    my_roi_patched = (
                        bbox.x + patch_width_full * x,
                        bbox.y + patch_height_full * y,
                        patch_width,
                        patch_height,
                    )

                    print(
                        "C" + str(channel),
                        "x =", x,
                        "y =", y,
                        "roi =", my_roi_patched,
                    )

                    ch = czidoc.read(
                        roi=my_roi_patched,
                        plane={"C": channel},
                    )

                    # czidoc.read retourne souvent une image de forme (Y, X, 1)
                    ch = np.asarray(ch)

                    if ch.ndim == 3:
                        ch = ch[..., 0]
                    else:
                        ch = np.squeeze(ch)

                    if downsampling_factor == 1:
                        ch_res = ch
                    else:
                        ch_res = ch[::downsampling_factor, ::downsampling_factor]

                    out_y0 = y * downsampled_patch_h
                    out_x0 = x * downsampled_patch_w

                    out_y1 = out_y0 + ch_res.shape[0]
                    out_x1 = out_x0 + ch_res.shape[1]

                    mosaic_image[out_y0:out_y1, out_x0:out_x1] = ch_res

            filename = (
                base_name
                + "_totalbbox_ds"
                + str(downsampling_factor)
                + "_C"
                + str(channel)
                + ".tiff"
            )

            output_path = os.path.join(pathout, filename)

            im = Image.fromarray(mosaic_image.astype(np.uint16))
            im.save(output_path)

            print("\nSaved:", output_path)


# ============================================================
# 3. LANCER LA CONVERSION
# ============================================================

if __name__ == "__main__":
    convert_czi_total_bbox_to_tiff(
        pathin=rootdir,
        czifilename=czifilename,
        pathout=outdir,
        patch_factor=patch_factor,
        downsampling_factor=downsampling_factor,
        full_patch_w_h=full_patch_w_h,
        channels=channels,
    )