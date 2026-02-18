import argparse
import os
import sys

sys.path.insert(0, "BIDS")

from python_scripts import czi_convert2 as czi
from czi_reader import MimosaReader
from ancpbids import BIDSLayout
import bids_manager as bm
import bids_metadata as bmeta


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
    parser.add_argument("-y", "--yaml", type=str, default="metadata.yml", help="Fichier YAML metadata")
    args = parser.parse_args()

    output_format = args.output_format.lower().strip()
    if output_format not in ("tif", "nii", "both"):
        raise ValueError("output_format doit etre 'tif', 'nii' ou 'both'")

    clean_output_path = args.output_path.rstrip("/")

    layout, dataset, bids_root_path = bm.initialize_dataset(clean_output_path, yaml_path=args.yaml)

    csv_path = "/DATA/mimosa/mimosa/externe_metadata/subjects_correspondence.csv"
    if os.path.exists(csv_path):
        MimosaReader.load_correspondence_table(csv_path)
        print(f"Table de correspondance chargee depuis {csv_path}")
    else:
        print(f"Attention: {csv_path} introuvable")

    downsampling_factor = 2 ** args.downsampling_factor

    sessions_by_sub = {}  
    files_to_process = []
    for root, dirs, files in os.walk(args.input_path):
        if  "sourcedata" in root or "derivatives" in root:
            continue
        for file in files:
            if file.endswith(".czi"):
                files_to_process.append((root, file))

    print(f"Nombre de fichiers trouves: {len(files_to_process)}")
    if len(files_to_process) == 0:
        print("ATTENTION: Aucun fichier .czi trouve")
        return
    
    samples_rows = []

    for input_dir, filename in files_to_process:
        full_input_path = os.path.join(input_dir, filename)

        with MimosaReader(full_input_path) as reader:
            if reader is None:
                continue
            summary = reader.get_summary()

        print(f"\n>>> Traitement de: {filename}")
        print(f"    Sujet: {summary['sub']}, Session(date): {summary['ses']}, Sample: {summary['sample']}")

        bm.create_sourcedata_links(full_input_path, summary["sub"], bids_root_path)

        layout = BIDSLayout(bids_root_path)

        czi_id = os.path.splitext(filename)[0]
        bids_info = bm.get_bids_info(layout, summary, bids_root_path, czi_id=czi_id)
        sample_id = f"sample-{bids_info['sample']}"
        participant_id = f"sub-{bids_info['sub']}"
        samples_rows.append({
            "sample_id": sample_id,
            "participant_id": participant_id
        })

        sub = bids_info["sub"]
        ses_id = f"ses-{bids_info['ses']}"
        acq_time = bids_info["acq_time"]
        sessions_by_sub.setdefault(sub, {})
        sessions_by_sub[sub][ses_id] = acq_time

        czi.czi2bitmapHPC(
            input_dir,
            filename,
            bids_root_path,
            bids_info,
            downsampling_factor,
            output_format,
            pipeline_name="downsampled",
            reader=reader
            )

    for sub, d in sessions_by_sub.items():
        rows = []
        for ses_id in sorted(d.keys()):  
            rows.append({"session_id": ses_id, "acq_time": d[ses_id]})
        bmeta.write_subject_sessions_tsv(bids_root_path, sub, rows)
        bmeta.write_samples_tsv(bids_root_path, samples_rows)
    print("\n[SUCCESS] Conversion terminee")


if __name__ == "__main__":
    main()