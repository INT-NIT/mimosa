import argparse
import os
import sys

# Ajout du dossier /BIDS au path pour que Python trouve les modules
sys.path.append(os.path.abspath("/BIDS"))

# Imports des modules locaux
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

    # 1. Initialisation BIDS (Dossier des Alias)
    layout, dataset = initialize_dataset(args.output_path)
    
    # 2. Gestion du stockage physique (Fichiers lourds)
    # Si non précisé, on crée un dossier "raw_data" à côté de l'output BIDS
    raw_output_path = args.raw_path if args.raw_path else args.output_path + "_raw_data"
    if not os.path.exists(raw_output_path):
        os.makedirs(raw_output_path)
        print(f"Dossier Raw créé : {raw_output_path}")

    downsampling_factor = 2 ** (args.downsampling_factor)
    
    # Liste des fichiers CZI
    czifilelist = [f for f in os.listdir(args.input_path) if f.endswith('.czi')]
    print(f"Nombre de fichiers trouvés : {len(czifilelist)}")

    for filename in czifilelist:
        full_input_path = os.path.join(args.input_path, filename)
        
        # 3. Extraction des métadonnées avec MimosaReader
        with MimosaReader(full_input_path) as reader:
            if reader is None: 
                continue
            summary = reader.get_summary()
            
            # 4. Calcul du chemin BIDS pour l'alias
            # get_bids_path renvoie (folder_path, root_name)
            bids_folder, bids_root = get_bids_path(layout, summary)
            
            print(f"\n>>> Traitement de : {filename}")
            print(f"    Sujet : {summary['sub']} | Session : {summary['ses']}")

            # 5. Conversion et création des alias simultanée
            # On passe bids_folder et bids_root pour que czi2bitmapHPC fasse les symlinks
            czi.czi2bitmapHPC(
                args.input_path, 
                filename, 
                raw_output_path, 
                downsampling_factor, 
                args.output_format,
                bids_folder=bids_folder,
                bids_root=bids_root
            )

            # 6. Écriture du sidecar JSON (obligatoire BIDS)
            # On le lie au premier chunk de l'alias pour la validation
            sample_json_path = os.path.join(bids_folder, bids_root + "_chunk-00_FLUO")
            write_bids_sidecar(sample_json_path, summary)

        # 7. Rafraîchissement du Layout
        # Crucial pour que le prochain fichier voie les runs précédents et s'incrémente
        layout.index()

    print("\n[SUCCESS] Conversion et création des alias terminées.")

if __name__ == "__main__":
    main()
