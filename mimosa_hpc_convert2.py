import argparse
import os
import sys

sys.path.insert(0, "BIDS")

from python_scripts import czi_convert2 as czi
from czi_reader import MimosaReader
from ancpbids import BIDSLayout
import bids_manager as bm


def dir_path(path):
    if os.path.isdir(path):
        return path
    raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")


def main():
    parser = argparse.ArgumentParser(description="Process for CZI conversion to BIDS")
    parser.add_argument("-i", "--input_path", type=dir_path, required=True, help="Path contenant les .czi")
    parser.add_argument("-f", "--output_format", type=str, required=True, help="tiff ou nii")
    parser.add_argument("-df", "--downsampling_factor", type=int, required=True, help="Facteur 2^N")
    parser.add_argument("-o", "--output_path", type=str, required=True, help="Root du Dataset BIDS")
    args = parser.parse_args()

    output_format = args.output_format.strip().lower()
    if output_format not in ("tiff", "nii"):
        raise ValueError("output_format doit être 'tiff' ou 'nii'")

    # Charger la table de correspondance
    csv_path = "subjects_correspondence.csv"
    if os.path.exists(csv_path):
        MimosaReader.load_correspondence_table(csv_path)
        print(f"Table de correspondance chargee depuis {csv_path}")
    else:
        print(f"Attention: {csv_path} introuvable")

    clean_output_path = args.output_path.rstrip("/")
    layout, dataset, bids_root_path = bm.initialize_dataset(clean_output_path)

    bm.initialize_derivatives(bids_root_path, pipeline_name="downsampled")

    downsampling_factor = 2 ** args.downsampling_factor

    files_to_process = []
    for root, dirs, files in os.walk(args.input_path):
        for file in files:
            if file.endswith(".czi"):
                files_to_process.append((root, file))

    print(f"Nombre de fichiers trouves: {len(files_to_process)}")
    if len(files_to_process) == 0:
        print("ATTENTION: Aucun fichier .czi trouve")
        return

    run_counter = {}  # compteur global pour run

    for input_dir, filename in files_to_process:
        full_input_path = os.path.join(input_dir, filename)

        with MimosaReader(full_input_path) as reader:
            if reader is None:
                continue
            summary = reader.get_summary()

        print(f"\n>>> Traitement de: {filename}")
        print(f"    Sujet: {summary['sub']}, Session: {summary['ses']}, Sample: {summary['sample']}")

        # 1) lien sourcedata
        bm.create_sourcedata_links(full_input_path, summary["sub"], bids_root_path)

        # 2) recharger layout (si tu relies run/acq à ce qui existe déjà)
        layout = BIDSLayout(bids_root_path)

        # 3) infos BIDS
        bids_info = bm.get_bids_info(layout, summary, bids_root_path)
        bids_info["summary_for_json"] = summary  # pour tes sidecars

        # 4) conversion (appel avec la bonne signature)
        czi.czi2bitmapHPC(
            pathin=input_dir,
            czifilename=filename,
            bids_root_path=bids_root_path,
            bids_info=bids_info,
            run_counter=run_counter,
            downsampling_factor=downsampling_factor,
            output_format=output_format,
            pipeline_name="downsampled",
        )

    print("\n[SUCCESS] Conversion terminee")


if __name__ == "__main__":
    main()