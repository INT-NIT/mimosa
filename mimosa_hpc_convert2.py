import argparse
import os
import sys

sys.path.append(os.path.abspath("/BIDS"))
from python_scripts import czi_convert2 as czi
sys.path.append(os.path.abspath("BIDS"))
from czi_reader import MimosaReader
from ancpbids import BIDSLayout
import bids_manager as bm 
from pylibCZIrw import czi as pyczi # lecture des .czi 

def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")

def main():
    parser = argparse.ArgumentParser(description='Process for CZI conversion to BIDS')
    parser.add_argument('-i', '--input_path', type=dir_path, required=True, help='Path contenant les .czi')
    parser.add_argument('-f', '--output_format', type=str, required=False, help='tiff ou nii (ignoré: on fait toujours les deux)')
    parser.add_argument('-df', '--downsampling_factor', type=int, required=True, help='Facteur 2^N')
    parser.add_argument('-o', '--output_path', type=str, required=True, help='Root of Dataset BIDS')
    parser.add_argument('-raw', '--raw_path', type=str, help='Path pour le stockage des fichiers lourds')
    args = parser.parse_args()
    
    # Charger la table de correspondance
    csv_path = 'subjects_correspondence.csv'
    if os.path.exists(csv_path):
        MimosaReader.load_correspondence_table(csv_path)
        print(f"Table de correspondance chargee depuis {csv_path}")
    else:
        print(f"Attention: {csv_path} introuvable")
    
    clean_output_path = args.output_path.rstrip("/")
    layout, dataset, bids_root_path = bm.initialize_dataset(clean_output_path)

    derivatives_path = bm.initialize_derivatives(bids_root_path, pipeline_name="downsampled")

    raw_output_path = args.raw_path if args.raw_path else clean_output_path + "_raw_data"
    if not os.path.exists(raw_output_path):
        os.makedirs(raw_output_path)
        print(f"Dossier raw_data cree: {raw_output_path}")
    
    downsampling_factor = 2 ** (args.downsampling_factor)
    
    files_to_process = []
    for root, dirs, files in os.walk(args.input_path):
        for file in files:
            if file.endswith('.czi'):
                files_to_process.append((root, file))
    
    print(f"Nombre de fichiers trouves: {len(files_to_process)}")
    if len(files_to_process) == 0:
        print("ATTENTION: Aucun fichier .czi trouve")
        return
    
    for input_dir, filename in files_to_process:
        full_input_path = os.path.join(input_dir, filename)
        
        with MimosaReader(full_input_path) as reader:
            if reader is None: 
                continue
            summary = reader.get_summary()
        
        print(f"\n>>> Traitement de: {filename}")
        print(f"    Sujet: {summary['sub']}, Session: {summary['ses']}, Sample: {summary['sample']}")
        
        # 1. Créer lien sourcedata
        bm.create_sourcedata_links(full_input_path, summary['sub'], bids_root_path)
        
        # 2. Recharger le layout pour voir les fichiers déjà créés
        layout = BIDSLayout(bids_root_path)

        # 3. Calculer infos BIDS de base (sans run, sans canal)
        bids_info = bm.get_bids_info(layout, summary, bids_root_path)
        
        # 4a. Conversion TIFF (pour BIDS principal - fichiers légers à visualiser)
        channels_info, nb_scenes, bids_infos_per_channel = czi.czi2bitmapHPC(
            input_dir,
            filename, 
            raw_output_path, 
            downsampling_factor, 
            "tiff",
            layout=layout,
            bids_info=bids_info,
            bids_root_path=bids_root_path
        )
        
        # 4b. Conversion NIfTI (pour derivatives - format analyse)
        czi.czi2bitmapHPC(
            input_dir,
            filename, 
            raw_output_path, 
            downsampling_factor, 
            "nii",
            layout=layout,
            bids_info=bids_info,
            bids_root_path=bids_root_path
        )
        
       
    
    
    
    print("\n[SUCCESS] Conversion terminee")

if __name__ == "__main__":
    main()