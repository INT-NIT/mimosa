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

    # 1. Initialisation BIDS
    # Astuce : enlève le slash final s'il existe pour éviter les chemins bizarres
    clean_output_path = args.output_path.rstrip("/")
    layout, dataset = initialize_dataset(clean_output_path)
    
    # 2. Gestion du stockage physique
    raw_output_path = args.raw_path if args.raw_path else clean_output_path + "_raw_data"
    if not os.path.exists(raw_output_path):
        os.makedirs(raw_output_path)
        print(f"Dossier Raw créé : {raw_output_path}")

    downsampling_factor = 2 ** (args.downsampling_factor)
    
    # --- CORRECTION ICI : Recherche récursive (os.walk) ---
    files_to_process = []
    for root, dirs, files in os.walk(args.input_path):
        for file in files:
            if file.endswith('.czi'):
                # On garde le dossier parent (root) et le nom du fichier
                files_to_process.append((root, file))

    print(f"Nombre de fichiers trouvés : {len(files_to_process)}")

    if len(files_to_process) == 0:
        print("ATTENTION : Aucun fichier .czi trouvé. Vérifiez le chemin d'entrée.")
        return

    # On boucle sur la liste des tuples (dossier, fichier)
    for input_dir, filename in files_to_process:
        full_input_path = os.path.join(input_dir, filename)
        
        # 3. Extraction métadonnées
        with MimosaReader(full_input_path) as reader:
            if reader is None: 
                continue
            summary = reader.get_summary()
            
            # 4. Calcul chemin BIDS
            bids_folder, bids_root = get_bids_path(layout, summary)
            
            print(f"\n>>> Traitement de : {filename}")
            
            # 5. Conversion
            # IMPORTANT : On passe 'input_dir' (le sous-dossier où est le fichier)
            # et non 'args.input_path' (la racine globale)
            czi.czi2bitmapHPC(
                input_dir,        # <-- Modifié ici
                filename, 
                raw_output_path, 
                downsampling_factor, 
                args.output_format,
                bids_folder=bids_folder,
                bids_root=bids_root
            )

            # 6. Sidecar JSON
            sample_json_path = os.path.join(bids_folder, bids_root + "_chunk-00_FLUO")
            write_bids_sidecar(sample_json_path, summary)

        # 7. Indexation
        layout.index()

    print("\n[SUCCESS] Conversion et création des alias terminées.")

if __name__ == "__main__":
    main()
