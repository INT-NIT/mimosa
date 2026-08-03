"""Convertit un CZI en images réduites AVEC zoom (ancienne méthode).

Extrait simplifié de czi2bitmapHPC. Sert à produire deux images à deux
facteurs de zoom différents, pour les comparer (par ex. dans FSLeyes).

Lancement :
    python convert_zoom_two_factors.py
(édite les chemins et les facteurs dans le bloc __main__ en bas)
"""

import os

import nibabel as nib
import numpy as np
import tifffile as tf
from pylibCZIrw import czi as pyczi


def czi_to_downsampled_zoom(pathin, czifilename, pathout,
                            downsampling_factor, output_format="nii"):
    """Réduit un CZI avec le zoom de la librairie (méthode ZEN).

    - downsampling_factor : le facteur (ex. 64, 256). zoom = 1 / facteur.
    - output_format       : "nii" ou "tiff".
    Une image est écrite par scène et par canal (C0 et C1).
    """
    czifile = os.path.join(pathin, czifilename)
    cziname = os.path.splitext(czifilename)[0]
    zoom_factor = 1.0 / downsampling_factor

    with pyczi.open_czi(czifile) as czidoc:
        scenes = czidoc.scenes_bounding_rectangle

        for i in range(len(scenes)):
            rect = scenes[i]
            roi = (rect[0], rect[1], rect[2], rect[3])
            print(f"Scene {i}: roi={roi}, zoom=1/{downsampling_factor}")

            # --- ICI le zoom : c'est ZEN qui réduit ---
            ch0 = czidoc.read(roi=roi, plane={"C": 0}, scene=i, zoom=zoom_factor)
            ch1 = czidoc.read(roi=roi, plane={"C": 1}, scene=i, zoom=zoom_factor)

            for channel, data in ((0, ch0), (1, ch1)):
                data = np.squeeze(data)          # [y, x, 1] -> [y, x]
                base = f"{cziname}_ds{downsampling_factor}_S{str(i).zfill(2)}_C{channel}"

                if output_format == "tiff":
                    tf.imwrite(os.path.join(pathout, base + ".tiff"),
                               data, imagej=True)
                    print("  ->", base + ".tiff")

                elif output_format == "nii":
                    # pour le NIfTI : on échange x et y (comme dans ton code)
                    img = nib.Nifti1Image(np.swapaxes(data, 0, 1), np.eye(4))
                    nib.save(img, os.path.join(pathout, base + ".nii.gz"))
                    print("  ->", base + ".nii.gz")


if __name__ == "__main__":
    # ---- À ADAPTER ----
    pathin = "/envau/work/nit/users/boudlal.h"          # dossier du CZI
    czifile = "MIO21100401_Cx_104_112_120_128.czi"       # nom du CZI
    pathout = "/envau/work/nit/users/boudlal.h/test_zoom_compare"  # dossier de sortie
    os.makedirs(pathout, exist_ok=True)

    # ---- Les deux facteurs de zoom à comparer ----
    facteur_1 = 64     # ex. res-6x
    facteur_2 = 256    # ex. res-8x

    print("=== Image 1 : zoom 1/%d ===" % facteur_1)
    czi_to_downsampled_zoom(pathin, czifile, pathout, facteur_1, output_format="nii")

    print("=== Image 2 : zoom 1/%d ===" % facteur_2)
    czi_to_downsampled_zoom(pathin, czifile, pathout, facteur_2, output_format="nii")

    print("\nTermine. Les deux versions sont dans :", pathout)
