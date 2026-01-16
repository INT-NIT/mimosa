import csv
import re
from pathlib import Path
from pylibCZIrw import czi as czirw

# =========================================================
# HELPERS
# =========================================================

def find_key_in_dict(data, target_key):
    if isinstance(data, dict):
        for k, v in data.items():
            if k.lower() == target_key.lower(): return v
            res = find_key_in_dict(v, target_key)
            if res: return res
    elif isinstance(data, list):
        for item in data:
            res = find_key_in_dict(item, target_key)
            if res: return res
    return None

def to_string(value):
    if value is None: return ""
    if isinstance(value, list) and value: return to_string(value[0])
    if isinstance(value, dict):
        return to_string(value.get("#text") or value.get("Value") or value.get("@Value"))
    return str(value).strip()

# =========================================================
# EXTRACTIONS
# =========================================================

def extract_microscope(metadata):
    # 1. Check Device
    devices = find_key_in_dict(metadata, "Device")
    if devices:
        for d in (devices if isinstance(devices, list) else [devices]):
            if to_string(d.get("@Id")) == "Microscope":
                return to_string(d.get("@Name"))
    # 2. Check Instrument
    instr = find_key_in_dict(metadata, "Instrument")
    if isinstance(instr, dict):
        micros = instr.get("Microscopes", {}).get("Microscope")
        if micros:
            for m in (micros if isinstance(micros, list) else [micros]):
                return to_string(m.get("@Name"))
    return "Unknown"

def extract_session(metadata):
    raw_date = find_key_in_dict(metadata, "AcquisitionDateAndTime") or find_key_in_dict(metadata, "CreationDate")
    if raw_date:
        m = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", to_string(raw_date))
        if m: return "".join(m.groups())
    return "1"

# =========================================================
# GÉNÉRATION DU CSV
# =========================================================

def generate_unique_mapping_csv(input_folder, output_csv):
    input_path = Path(input_folder)
    all_czis = list(input_path.rglob("*.czi"))
    unique_combinations = set()

    print(f"Analyse de {len(all_czis)} fichiers...")

    for f in all_czis:
        try:
            with czirw.open_czi(str(f)) as doc:
                meta = doc.metadata
            
            # --- NOM DU SUJET : On prend le nom du dossier parent ---
            # Si le fichier est dans /DATA/mimosa/Fenouil/file.czi -> subject_name = "Fenouil"
            subject_name = f.parent.name 
            
            session = extract_session(meta)
            scope = extract_microscope(meta)
            
            # --- NOM DU SAMPLE : Cx ou Sam ---
            sample = "Cx" if any(x in f.name.lower() for x in ["cortex", "cx"]) else "Sam"

            unique_combinations.add((subject_name, session, sample, scope))
        except:
            continue

    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Subject_Name", "Session_Date", "Sample_Type", "Microscope"])
        
        # Tri pour un CSV propre
        for row in sorted(list(unique_combinations)):
            writer.writerow(row)

    print(f"Succès ! Fichier CSV créé : {output_csv}")

if __name__ == "__main__":
    # Remplace par tes vrais chemins
    IN = "/DATA/mimosa/original-dataset"
    OUT = "correspondance_sujets.csv"
    
    generate_unique_mapping_csv(IN, OUT)