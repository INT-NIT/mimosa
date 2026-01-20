import os
import shutil
from pathlib import Path

# Chemins
src_base = Path("/envau/work/nit/users/boudlal.h/original-dataset")
dst_base = Path("/envau/work/nit/users/boudlal.h/BIDS_test")

def run_test():
    # 1. Créer la description du dataset (obligatoire pour le validateur)
    dst_base.mkdir(parents=True, exist_ok=True)
    with open(dst_base / "dataset_description.json", "w") as f:
        f.write('{"Name": "Test Fenouil", "BIDSVersion": "1.8.0", "DatasetType": "raw"}')

    # 2. On prend un fichier exemple (Fenouil)
    # Adapte ce chemin vers un vrai fichier existant
    source_file = src_base / "1-Fenouil-MTO10092101/MTO10092101_Cx_280-288.czi"
    
    if not source_file.exists():
        print(f"Erreur : Le fichier {source_file} est introuvable.")
        return

    # Structure BIDS cible
    sub = "sub-Fenouil"
    ses = "ses-20230417"
    suffix = "microscopy"
    
    # On crée le dossier de modalité OBLIGATOIRE
    dest_dir = dst_base / sub / ses / "micr"
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # Nom de fichier BIDS valide
    dest_file = dest_dir / f"{sub}_{ses}_sample-Cx_run-01_{suffix}.czi"
    dest_json = dest_dir / f"{sub}_{ses}_sample-Cx_run-01_{suffix}.json"

    # Copie (pour éviter les erreurs de lien pendant le test)
    print(f"Test de copie vers : {dest_file}")
    shutil.copy2(source_file, dest_file)
    
    # Création d'un JSON vide pour accompagner le CZI
    with open(dest_json, "w") as f:
        f.write('{"Fluorescence": "True"}')

    print("\n--- TEST TERMINE ---")
    print(f"Vérifie maintenant avec : tree {dst_base}")

run_test()