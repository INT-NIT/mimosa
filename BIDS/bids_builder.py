import ancpbids
from pathlib import Path
from czi_reader import MimosaReader

class MimosaBidsBuilder:
    def __init__(self, bids_root):
        self.bids_root = Path(bids_root)
        self.bids_root.mkdir(parents=True, exist_ok=True)
        
        # 1. On charge le dataset (Fonction de ta liste API)
        self.dataset = ancpbids.load_dataset(str(self.bids_root))
        
        # 2. Configuration de la description (API : dataset_description)
        # On s'assure que l'objet existe avant de le remplir
        if not self.dataset.dataset_description:
            # Si None, on laisse ancpbids initialiser par défaut lors du save
            pass
        
        self.acq_map = {}
        self.run_counts = {}

    def add_file(self, info):
        # 3. Création des structures (API : create_subject / create_session)
        # Ces fonctions préparent les dossiers dans l'objet dataset
        sub_id = info['sub']
        ses_id = info['ses']
        
        subject = self.dataset.create_subject(label=sub_id)
        session = subject.create_session(label=ses_id)

        # 4. Remplissage des métadonnées (Ce qui a créé tes fichiers participants !)
        subject.species = info['animal'].get('species', 'n/a')
        subject.age = info['animal'].get('age', 'n/a')
        subject.sex = info['animal'].get('sex', 'n/a')

        # 5. Calcul Acquisition / Run
        key = (sub_id, ses_id)
        if key not in self.acq_map: self.acq_map[key] = []
        if info['acq_sig'] not in self.acq_map[key]: self.acq_map[key].append(info['acq_sig'])
        acq_id = self.acq_map[key].index(info['acq_sig']) + 1
        
        run_key = (sub_id, ses_id, acq_id)
        self.run_counts[run_key] = self.run_counts.get(run_key, 0) + 1
        run_label = f"{self.run_counts[run_key]:02d}"

        # 6. Création de l'Artifact (C'est ça qui crée les dossiers sub-XX/ses-XX/micr/)
        artifact = session.create_artifact()
        artifact.add_entity("sample", "Cx")
        artifact.add_entity("acq", str(acq_id))
        artifact.add_entity("run", run_label)
        artifact.suffix = "microscopy"
        artifact.extension = ".czi"

        print(f"✅ Planifié : sub-{sub_id} | ses-{ses_id} | run-{run_label}")

    def save(self):
        # 7. Sauvegarde (Fonction de ta liste API : save_dataset)
        # Cette fonction transforme tout l'objet "dataset" en dossiers réels
        ancpbids.save_dataset(self.dataset, str(self.bids_root))

def main():
    SOURCE_DIR = "/envau/work/nit/users/boudlal.h/original-dataset"
    BIDS_ROOT = "/envau/work/nit/users/boudlal.h/BIDS_dataset"

    builder = MimosaBidsBuilder(BIDS_ROOT)

    print(f"--- Analyse des fichiers dans {SOURCE_DIR} ---")
    files = list(Path(SOURCE_DIR).rglob("*.czi"))
    
    for czi_file in files:
        with MimosaReader(czi_file) as reader:
            if reader and reader.metadata:
                data = reader.get_summary() 
                builder.add_file(data)

    print("\n--- Génération de l'arborescence BIDS ---")
    builder.save()
    print(f"🏁 Terminé ! Vérifie le dossier : {BIDS_ROOT}")

if __name__ == "__main__":
    main()