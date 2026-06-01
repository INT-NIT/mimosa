import argparse
import os


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
    parser.add_argument("-df", "--downsampling_factor", type=int,   required=True,  help="downsampling factor e.x: 4 ")
    parser.add_argument("-o", "--output_path",       type=str,      required=True,  help="BIDS dataset root")
    parser.add_argument("-y", "--yaml",              type=str,      default="metadata.yml", help="metadata YAML file")
    parser.add_argument("--original_thickness",required=False,type=float,default=100,help="Histological section thickness in micrometers")
    args = parser.parse_args()

    output_format = args.output_format.lower().strip()
    if output_format not in ("tif", "nii", "both"):
        raise ValueError("output_format must be 'tif', 'nii' or 'both'")

    clean_output_path = args.output_path.rstrip("/")

    downsampling_factor = args.downsampling_factor
    res_label = f"{downsampling_factor}x"
    pipeline_name = f"2D-downsampled_res-{res_label}"

    bids_root_path = bm.initialize_dataset(
        clean_output_path,
        yaml_path=args.yaml,
        output_format=output_format,
        pipeline_names=[pipeline_name],
    )
    cfg = bmeta.load_metadata_config(args.yaml)
    slice_position_map = bmeta.get_slice_position_map_from_config(cfg)

    MimosaReader.load_correspondence_from_yaml(cfg)

    session = bm.BIDSSession(bids_root_path)

    files_to_process = []
    sessions_by_sub = {}
    samples_rows    = []

    for entry in cfg.get("samples", {}).get("entries", []):
        subject_path = entry["path"]

        print("DEBUG YAML subject path:", subject_path)

        if not os.path.exists(subject_path):
            print(f"WARNING: path not found: {subject_path}")
            continue

        for sample in entry.get("samples", []):
            for file_entry in sample.get("files", []):
                filename = file_entry.get("filename")
                slices = file_entry.get("slices", [])

                if not filename:
                    continue

                if not filename.endswith(".czi"):
                    continue

                if not slices:
                    print(f"  SKIP YAML file without slices: {filename}")
                    continue

                full_path = os.path.join(subject_path, filename)

                if not os.path.exists(full_path):
                    print(f"WARNING: file listed in YAML but not found: {full_path}")
                    continue

                files_to_process.append((subject_path, filename))
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
                czi.czi2bitmapHPC(
                    input_dir,
                    filename,
                    bids_root_path,
                    bids_info,
                    downsampling_factor,
                    output_format,
                    pipeline_name=pipeline_name,
                    reader=reader,
                    slice_position_map=slice_position_map,
                    original_thickness=args.original_thickness,
                )

        except Exception as e:
            print(f"    ERROR processing {filename}: {e}")
            continue

    for sub, d in sessions_by_sub.items():
        rows = [
            {"session_id": ses_id, "acq_time": d[ses_id]}
            for ses_id in sorted(d.keys())
        ]

        bmeta.write_subject_sessions_tsv(
            bids_root_path,
            sub,
            rows,
        )

        bmeta.write_subject_sessions_tsv(
            os.path.join(bids_root_path, "derivatives", pipeline_name),
            sub,
            rows,
        )

    bmeta.write_samples_tsv(bids_root_path, samples_rows)

    print("\n[SUCCESS] Conversion done.")

if __name__ == "__main__":
    main()