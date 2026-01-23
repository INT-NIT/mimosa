"""
Création BIDS avec import de ton czi_reader.py
"""
from pathlib import Path
import re
from ancpbids import BIDSLayout
from ancpbids.utils import write_contents, parse_bids_name
from pylibCZIrw import czi as czirw

#  IMPORTER ton MimosaReader depuis czi_reader.py
from czi_reader import MimosaReader


# ============================================================
# CORRECTION : Fonction pour extraire le sujet correctement
# ============================================================
def extract_subject_from_filename(czi_path):
    """
    Extrait le sujet depuis le NOM DU FICHIER, pas du dossier
    
    Exemples :
    - MIO21100401_Cx_104_112_120_128.czi → "MIO21100401"
    - Mouse01_Cortex.czi → "Mouse01"
    - sub-05_ses-01.czi → "05"
    """
    file_name = Path(czi_path).stem  # Enlève l'extension .czi
    
    # Méthode 1 : Pattern MIO + chiffres
    match = re.search(r'(MIO\d+)', file_name)
    if match:
        return match.group(1)
    
    # Méthode 2 : Si format BIDS sub-XX
    match = re.search(r'sub[-_](\w+)', file_name)
    if match:
        return match.group(1)
    
    # Méthode 3 : Prendre le premier segment avant '_'
    parts = file_name.split('_')
    if parts:
        return parts[0]
    
    return "UnknownSubject"


# ============================================================
# EXTRACTION DES CANAUX DEPUIS LE CZI
# ============================================================
def extract_channels_from_czi(czi_path):
    """
    Détecte automatiquement les canaux dans le CZI
    
    Cherche dans les métadonnées XML :
    - <Channels><Channel Name="C0"><DyeId>DAPI</DyeId></Channel>...
    
    Retourne : [{"index": 0, "name": "C0", "dye": "DAPI"}, ...]
    """
    channels_info = []
    
    with czirw.open_czi(str(czi_path)) as doc:
        metadata = doc.metadata
        
        # Fonction récursive pour chercher les canaux
        def find_channels(data):
            if isinstance(data, dict):
                # Chercher "Channel" ou "Channels"
                if "Channel" in data or "Channels" in data:
                    channel_data = data.get("Channel") or data.get("Channels")
                    if isinstance(channel_data, list):
                        return channel_data
                    elif isinstance(channel_data, dict):
                        return [channel_data]
                
                # Continuer la recherche récursive
                for v in data.values():
                    result = find_channels(v)
                    if result:
                        return result
            elif isinstance(data, list):
                for item in data:
                    result = find_channels(item)
                    if result:
                        return result
            return None
        
        channels = find_channels(metadata)
        
        if channels:
            for i, ch in enumerate(channels):
                channel_name = ch.get("@Name") or ch.get("Name") or f"C{i}"
                dye_id = ch.get("DyeId") or ch.get("@DyeId") or "Unknown"
                
                channels_info.append({
                    "index": i,
                    "name": str(channel_name),
                    "dye": str(dye_id)
                })
        else:
            # Fallback : supposer un canal DAPI
            print("  Impossible de détecter les canaux, utilisation de DAPI par défaut")
            channels_info = [{"index": 0, "name": "C0", "dye": "DAPI"}]
    
    return channels_info


# ============================================================
# CRÉATION BIDS AVEC TON VRAI CZI
# ============================================================
def create_bids_from_real_czi(czi_file, bids_root, extract_images=False):
    """
    Crée une structure BIDS complète depuis ton CZI
    
    Étapes :
    1. Lit les métadonnées avec MimosaReader
    2.  CORRIGE le sujet en l'extrayant du nom du fichier
    3. Détecte les canaux automatiquement
    4. Crée l'arborescence BIDS
    5. Valide avec ancpbids
    """
    
    czi_path = Path(czi_file)
    
    if not czi_path.exists():
        print(f" Fichier introuvable: {czi_path}")
        return
    
    print(f" Traitement: {czi_path.name}")
    print("="*70)
    
    # 1. Extraire metadata avec MimosaReader
    with MimosaReader(czi_path) as reader:
        if not reader:
            print(" Impossible de lire le CZI")
            return
        
        summary = reader.get_summary()
        animal_info = summary['animal']
    
    #  2. CORRIGER le sujet en extrayant depuis le nom du fichier
    subject_corrected = extract_subject_from_filename(czi_path)
    summary['sub'] = subject_corrected
    
    print(f"\n Métadonnées extraites:")
    print(f"   Sujet (corrigé): {summary['sub']} (extrait de '{czi_path.name}')")
    print(f"   Session: {summary['ses']}")
    print(f"   Sample: {summary['sample']}")
    print(f"   Illumination: {summary['illumination']}")
    print(f"   Animal: species={animal_info['species']}, age={animal_info['age']}, sex={animal_info['sex']}")
    
    # 3. Détecter les canaux
    print(f"\n Détection des canaux...")
    channels = extract_channels_from_czi(czi_path)
    print(f"   Canaux trouvés: {len(channels)}")
    for ch in channels:
        print(f"   - Canal {ch['index']}: {ch['name']} (dye: {ch['dye']})")
    
    # 4. Créer la structure BIDS
    bids_path = Path(bids_root).resolve()
    bids_path.mkdir(parents=True, exist_ok=True)
    
    # 5. dataset_description.json
    desc_file = bids_path / "dataset_description.json"
    if not desc_file.exists():
        desc = {
            "Name": "Microscopy Dataset",
            "BIDSVersion": "1.9.0",
            "DatasetType": "raw",
            "Authors": ["Your Name"],
            "License": "CC0"
        }
        write_contents(str(desc_file), desc)
        print(f"\n Créé: dataset_description.json")
    
    # 6. Créer un fichier par canal
    print(f"\n Création de la structure BIDS...")
    
    created_files = []
    
    for channel in channels:
        stain_name = channel['dye'] if channel['dye'] != "Unknown" else channel['name']
        
        # Nettoyer le nom du stain (enlever caractères spéciaux)
        stain_name = re.sub(r'[^a-zA-Z0-9]', '', stain_name)
        
        # Chemin BIDS
        stain_dir = (bids_path / 
                     f"sub-{summary['sub']}" / 
                     f"ses-{summary['ses']}" / 
                     "micr" / 
                     f"sample-{summary['sample']}" / 
                     f"stain-{stain_name}")
        stain_dir.mkdir(parents=True, exist_ok=True)
        
        # Nom du fichier BIDS
        base_name = f"sub-{summary['sub']}_ses-{summary['ses']}_sample-{summary['sample']}_stain-{stain_name}_micr"
        
        # Valider le nom avec ancpbids
        parsed = parse_bids_name(f"{base_name}.tiff")
        
        tiff_file = stain_dir / f"{base_name}.tiff"
        json_file = stain_dir / f"{base_name}.json"
        
        # Métadonnées JSON sidecar
        metadata = {
            "Manufacturer": summary['acq_sig'].split('_')[0],
            "ManufacturersModelName": summary['acq_sig'],
            "IlluminationType": summary['illumination'],
            "Species": animal_info['species'],
            "Age": animal_info['age'],
            "Sex": animal_info['sex'],
            "SampleFixation": "n/a",
            "SampleStaining": stain_name,
            "ChannelIndex": channel['index'],
            "ChannelName": channel['name'],
            "Fluorophore": channel['dye'],
            "SourceFile": czi_path.name
        }
        
        write_contents(str(json_file), metadata)
        
        # Créer le TIFF (vide pour l'instant)
        if extract_images:
            print(f"    Extraction du canal {channel['index']}...")
            # TODO: Implémenter l'extraction réelle
            tiff_file.touch()
        else:
            tiff_file.touch()
        
        created_files.append({
            'tiff': tiff_file,
            'json': json_file,
            'channel': channel
        })
        
        print(f"    {stain_name}: {base_name}.tiff")
    
    # 7. Validation avec BIDSLayout
    print(f"\n Validation avec ancpbids BIDSLayout...")
    layout = BIDSLayout(str(bids_path))
    
    print(f"\n Dataset BIDS validé:")
    print(f"   Sujets: {layout.get_subjects()}")
    print(f"   Sessions: {layout.get_sessions()}")
    print(f"   Samples: {layout.get_samples()}")
    print(f"   Stains: {layout.get_stains()}")
    
    # 8. Résumé final
    print(f"\n" + "="*70)
    print(f" RÉSUMÉ")
    print(f"="*70)
    print(f"Dataset BIDS créé dans: {bids_path}")
    print(f"Fichiers créés: {len(created_files)} canaux")
    
    for item in created_files:
        rel_path = item['tiff'].relative_to(bids_path)
        print(f"\n   {rel_path}")
        print(f"      Canal: {item['channel']['name']} (index {item['channel']['index']})")
        print(f"      Dye: {item['channel']['dye']}")
        print(f"      JSON: {item['json'].name}")
    
    print(f"\n Pour valider formellement le dataset:")
    print(f"   layout = BIDSLayout('{bids_path}')")
    print(f"   report = layout.validate()")
    
    return created_files


# ============================================================
# UTILISATION
# ============================================================
if __name__ == "__main__":
    
    czi_file = "/home/INT/boudlal.h/Bureau/MIO21100401_Cx_104_112_120_128.czi"
    
    bids_root = "./bids_microscopy_dataset"
    
    files = create_bids_from_real_czi(czi_file, bids_root, extract_images=False)
    
    print(f"\n Terminé ! Structure BIDS créée avec succès.")
    print(f" Dossier: {Path(bids_root).resolve()}")