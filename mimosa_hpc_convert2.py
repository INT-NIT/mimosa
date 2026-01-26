import argparse
import os
import sys

sys.path.append(os.path.abspath("/BIDS"))
from python_scripts import czi_convert2 as czi
sys.path.append(os.path.abspath("BIDS"))
from czi_reader import MimosaReader
from bids_manager import initialize_dataset, get_bids_path, write_bids_sidecar

def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")

def main():
    parser = argparse.ArgumentParser(description='Process for CZI conversion to BIDS with Aliases')
    parser.add_argument('-i', '--input_path', type=dir_path, required=True, help='Path contenant les .czi')
    parser.add_argument('-f', '--output_format', type=str, required=True, help='tiff ou nii')
    parser.add_argument('-df', '--downsampling_factor', type=int, required=True, help='Facteur 2^N')
    parser.add_argument('-o', '--output_path', type=str, required=True, help='Root du Dataset BIDS (Alias)')
    parser.add_argument('-raw', '--raw_path', type=str, help='Path pour le stockage des fichiers lourds')
    args = parser.parse_args()
    
    # Charger la table de correspondance automatiquement
    csv_path = 'subjects_correspondence.csv'
    if os.path.exists(csv_path):
        MimosaReader.load_correspondence_table(csv_path)
        print(f"Table de correspondance chargee depuis {csv_path}")
    else:
        print(f"Attention: {csv_path} introuvable, utilisation methode par defaut")
    
    clean_output_path = args.output_path.rstrip("/")
    
    # FIX: Récupérer bids_root_path depuis initialize_dataset
    layout, dataset, bids_root_path = initialize_dataset(clean_output_path)
    
    raw_output_path = args.raw_path if args.raw_path else clean_output_path + "_raw_data"
    if not os.path.exists(raw_output_path):
        os.makedirs(raw_output_path)
        print(f"Dossier Raw cree : {raw_output_path}")
    
    downsampling_factor = 2 ** (args.downsampling_factor)
    
    files_to_process = []
    for root, dirs, files in os.walk(args.input_path):
        for file in files:
            if file.endswith('.czi'):
                files_to_process.append((root, file))
    
    print(f"Nombre de fichiers trouves : {len(files_to_process)}")
    if len(files_to_process) == 0:
        print("ATTENTION : Aucun fichier .czi trouve. Verifiez le chemin d'entree.")
        return
    
    for input_dir, filename in files_to_process:
        full_input_path = os.path.join(input_dir, filename)
        
        with MimosaReader(full_input_path) as reader:
            if reader is None: 
                continue
            summary = reader.get_summary()
        
        # FIX: Passer bids_root_path en paramètre
        bids_folder, bids_root = get_bids_path(layout, summary, bids_root_path)
        
        print(f"\n>>> Traitement de : {filename}")
        
        czi.czi2bitmapHPC(
            input_dir,
            filename, 
            raw_output_path, 
            downsampling_factor, 
            args.output_format,
            bids_folder=bids_folder,
            bids_root=bids_root
        )
        
        sample_json_path = os.path.join(bids_folder, bids_root + "_chunk-00_FLUO")
        write_bids_sidecar(sample_json_path, summary)
    
    print("\n[SUCCESS] Conversion et creation des alias terminees.")

if __name__ == "__main__":
    main()