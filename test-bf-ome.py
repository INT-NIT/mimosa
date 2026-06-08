#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
from pathlib import Path


def convert_czi_to_ome_tiff(input_czi: str, output_ome_tiff: str | None = None):
    input_path = Path(input_czi)

    if not input_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {input_path}")

    if input_path.suffix.lower() != ".czi":
        print("Attention : le fichier ne finit pas par .czi")

    if output_ome_tiff is None:
        output_path = input_path.with_suffix(".ome.tiff")
    else:
        output_path = Path(output_ome_tiff)

    cmd = [
        "bfconvert",
        "-overwrite",
        str(input_path),
        str(output_path),
    ]

    print("Commande lancée :")
    print(" ".join(cmd))

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    print("\n--- STDOUT ---")
    print(result.stdout)

    print("\n--- STDERR ---")
    print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError("Erreur pendant la conversion avec bfconvert.")

    print("\nConversion terminée.")
    print(f"Fichier créé : {output_path}")

    return output_path


def validate_ome_tiff(path: str):
    import tifffile

    with tifffile.TiffFile(path) as tf:
        print("\nValidation OME-TIFF :")
        print("is_ome:", tf.is_ome)
        print("Nombre de pages:", len(tf.pages))

        if tf.ome_metadata is not None:
            print("OME metadata trouvée: oui")
            print("Longueur OME-XML:", len(tf.ome_metadata))
            print("\nDébut du OME-XML :")
            print(tf.ome_metadata[:1000])
        else:
            print("OME metadata trouvée: non")


def main():
    if len(sys.argv) < 2:
        print("Utilisation :")
        print("    python convert_czi_bioformats.py fichier.czi")
        print("")
        print("Ou avec un nom de sortie :")
        print("    python convert_czi_bioformats.py fichier.czi sortie.ome.tiff")
        sys.exit(1)

    input_czi = sys.argv[1]

    output_ome_tiff = None
    if len(sys.argv) >= 3:
        output_ome_tiff = sys.argv[2]

    output_path = convert_czi_to_ome_tiff(input_czi, output_ome_tiff)

    try:
        validate_ome_tiff(str(output_path))
    except ImportError:
        print("\n`tifffile` n'est pas installé, validation ignorée.")
        print("Tu peux l'installer avec : pip install tifffile")


if __name__ == "__main__":
    main()