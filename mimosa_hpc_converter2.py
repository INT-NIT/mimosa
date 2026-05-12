import argparse
import os
import sys


from python_scripts import czi_convert2 as czi
from BIDS.czi_reader import MimosaReader  
from BIDS import bids_manager as bm
from BIDS import bids_metadata as bmeta


def dir_path(path):
    if os.path.isdir(path):
        return path
    raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")


def main():
    parser = argparse.ArgumentParser(description="Process for CZI conversion to BIDS")
    parser.add_argument("-f", "--output_format",     type=str,      required=True,  help="tif, nii or both")
    parser.add_argument("-df", "--downsampling_factor", type=int,   required=True,  help="factor 2^N")
    parser.add_argument("-o", "--output_path",       type=str,      required=True,  help="BIDS dataset root")
    parser.add_argument("-y", "--yaml",              type=str,      default="metadata.yml", help="metadata YAML file")
    args = parser.parse_args()

    output_format = args.output_format.lower().strip()
    if output_format not in ("tif", "nii", "both"):
        raise ValueError("output_format must be 'tif', 'nii' or 'both'")

    clean_output_path = args.output_path.rstrip("/")

    bids_root_path = bm.initialize_dataset(clean_output_path, yaml_path=args.yaml, output_format=output_format)

    cfg = bmeta.load_metadata_config(args.yaml)

    cfg = bmeta.update_yaml_with_slices(args.yaml)

    MimosaReader.load_correspondence_from_yaml(cfg)

    session = bm.BIDSSession(bids_root_path)

    downsampling_factor = 2 ** args.downsampling_factor

    files_to_process = []
    sessions_by_sub = {}
    samples_rows    = []

    for entry in cfg.get("samples", {}).get("entries", []):
        subject_path = entry["path"]   #  depuis le YAML
        
        if not os.path.exists(subject_path):
            print(f"WARNING: path not found: {subject_path}")
            continue
        
        for root, dirs, files in os.walk(subject_path):
            if "sourcedata" in root or "derivatives" in root:
                continue
            for file in files:
                if file.endswith(".czi"):
                    files_to_process.append((root, file))
        
    for input_dir, filename in files_to_process:
        full_input_path = os.path.join(input_dir, filename)
        czi_id          = os.path.splitext(filename)[0]

        print(f"\n>>> Processing: {filename}")

        try:
            with MimosaReader(full_input_path) as reader:
                if reader is None:
                    print(f"    SKIP: cannot open {filename}")
                    continue
                summary = reader.get_summary()

                print(f"    Subject: {summary['sub']}, Date: {summary['acq_time']}, Sample: {summary['sample']}")

                bm.create_sourcedata_links(full_input_path, summary["sub"], bids_root_path)
                bids_info = session.get_bids_info(
                    summary_meta=summary,
                    czi_id=czi_id,
                    section_idx=None   # sera mis à jour dans czi_convert2 pour chaque scène
                )

                participant_id = f"sub-{bids_info['sub']}"
                slide_num = len([r for r in samples_rows 
                                if r['sample_type'] == 'technical sample' 
                                and r['participant_id'] == participant_id]) + 1
                slide_id = f"sample-slide{slide_num:02d}"
                              
                samples_rows.append({
                    "sample_id":      slide_id,
                    "participant_id": f"sub-{bids_info['sub']}",
                    "sample_type":    "technical sample",
                    "derived_from":   "n/a",
                    "source_filename": filename,
                })

                slices = bmeta.get_slices_for_file(cfg, filename)  # liste des slices ex: [176, 184, 192]
                for slice_num in slices:
                    samples_rows.append({
                        "sample_id":      f"sample-section{slice_num}",
                        "participant_id": f"sub-{bids_info['sub']}",
                        "sample_type":    "tissue",
                        "derived_from":   slide_id,
                        "source_filename": "n/a",
                    })
                sub     = bids_info["sub"]
                ses_id  = f"ses-{bids_info['ses']}"
                sessions_by_sub.setdefault(sub, {})
                sessions_by_sub[sub][ses_id] = bids_info["acq_time"]
                raw_folder = bm.get_raw_micr_folder(bids_root_path, bids_info)
                bmeta.create_micr_json(
                    micr_folder  = raw_folder,
                    manufacturer = reader.get_manufacturer(),
                    illumination = reader.get_illumination_type(),
                    cfg          = cfg   # ← cfg est dispo ici !
                )
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

        except Exception as e:
            print(f"    ERROR processing {filename}: {e}")
            continue

    for sub, d in sessions_by_sub.items():
        rows = [{"session_id": ses_id, "acq_time": d[ses_id]} for ses_id in sorted(d.keys())]
        bmeta.write_subject_sessions_tsv(bids_root_path, sub, rows)
    
    bmeta.write_samples_tsv(bids_root_path, samples_rows)

    print("\n[SUCCESS] Conversion done.")


if __name__ == "__main__":
    main()