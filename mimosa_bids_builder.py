import os 
import json 
import shutil # pour copier les fichiers 
from datetime import datetime # pour horodater ce qu'on génère
from pylibCZIrw import czi as pyczi 

# variables globales 
PROJECT_NAME ="Mimosa"
BIDS_VERSION="1.9.0"
CZI_DIR="/DATA/dataset/"
CONVERTER_DIR = "/DATA/mimosa/renamed"
RESLICER_DIR = "/DATA/Projects/MIMOSA/reslicer_output/"
BIDS_DIR = "/DATA/mimosa/BIDS_dataset/"

def make_dirs(path):
    if not os.path.exists(path):
        os.makedirs(path)


def write_json(path,content):
    with open(path,"w") as f :
        json.dump(content,f,indent=4)


def create_global_structure():
    make_dirs(BIDS_DIR)

    # preparer le contenu de dataset_bids_description.json
    global_json = {
        "Name": PROJECT_NAME, # prendre chaque nom du sujet etudié 
        "BIDSVersion": BIDS_VERSION,
        "DatasetType": "raw",
        "GeneratedDate": datetime.now().isoformat()
    }

    # ecrire ce JSON à la racine de BIDS car BIDS impose des fichiers racine 
    write_json(os.path.join(BIDS_DIR, "dataset_bids_description.json"), global_json)

# Copie des czi + extraction des métadonnées Zeiss 
def process_czi_files(subject_id):
    # creer sub-Marmot/sourcedata/ → où iront les fichiers .czi
    sub_dir = os.path.join(BIDS_DIR, f"sub-{subject_id}")
    source_dir = os.path.join(sub_dir, "sourcedata")
    # creer sub-Marmot/sourcedata/metadata/ → où iront les .json de métadonnées
    meta_dir = os.path.join(source_dir, "metadata")
    make_dirs(meta_dir)
    # copier chaque .czi dans le dossier sourcedata
    for f in os.listdir(CZI_DIR):
        if f.endswith(".czi"):
            src = os.path.join(CZI_DIR, f)
            dst = os.path.join(source_dir, f)
            shutil.copy2(src, dst)
            try:
                with pyczi.open_czi(src) as czidoc:
                    metadata = czidoc.metadata
                json_name = f"sub-{subject_id}_{f.replace('.czi', '_metadata.json')}"
                write_json(os.path.join(meta_dir, json_name), metadata)
            except Exception as e:
                print(f"Impossible de lire les métadonnées pour {f}: {e}")

# organiser les fichiers 2D nii et nifti
