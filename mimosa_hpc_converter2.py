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
    parser.add_argument(
        "-df", "--downsampling_factor", type=str, required=True,
        help=(
            "Downsampling exponent(s), factor = 2**exponent. "
            "Accepts a single value (e.g. 4) or a comma separated list "
            "(e.g. 4,6,8). Several resolutions cost one single native read."
        ),
    )
    parser.add_argument("-o", "--output_path",       type=str,      required=True,  help="BIDS dataset root")
    parser.add_argument("-y", "--yaml",              type=str,      default="metadata.yml", help="metadata YAML file")
    parser.add_argument("-original_thickness",required=False,type=float,default=100,help="Histological section thickness in micrometers")
    parser.add_argument("-reorient",required=False,default="none",help="Reference reorientation used to compute SFormMatrix for 2D slices")
    parser.add_argument(
        "--threads", type=int, default=czi.READ_THREADS,
        help=(
            "Threads used to produce ONE image: its bands are read and reduced "
            "concurrently. This is the setting that makes a single NIfTI come "
            "out faster. Measured 7.3 s -> 3.3 s on 4 cores. Set it to your "
            "core count; going past it stops helping. Use 1 to disable."
        ),
    )
    parser.add_argument(
        "--block-value", type=str, default="decimate", choices=("decimate", "mean"),
        help=(
            "How to reduce each native block. "
            "'decimate' keeps the native pixel k*f, bit for bit "
            "(desc-downsampled). 'mean' averages the f*f native block, which "
            "is more accurate for quantification (desc-downsampledavg). "
            "Both are computed from native data: the ZEN pyramid is never used."
        ),
    )
    args = parser.parse_args()

    output_format = args.output_format.lower().strip()
    if output_format not in ("tif", "nii", "both"):
        raise ValueError("output_format must be 'tif', 'nii' or 'both'")

    clean_output_path = args.output_path.rstrip("/")

    downsampling_factor = sorted(
        {
            int(token)
            for token in str(args.downsampling_factor).replace(";", ",").split(",")
            if token.strip()
        }
    )
    if not downsampling_factor:
        raise ValueError("At least one downsampling exponent is required")

    res_label = {exponent: f"{exponent}x" for exponent in downsampling_factor}
    print("Exported resolutions:", ", ".join(res_label.values()))
    print("Block value        :", args.block_value)
    print("Threads            :", args.threads)

    bids_root_path = bm.initialize_dataset(
        clean_output_path,
        yaml_path=args.yaml,
        output_format=output_format,
    )
    cfg = bmeta.load_metadata_config(args.yaml)
    bmeta.update_yaml_with_slices(args.yaml)
    cfg = bmeta.load_metadata_config(args.yaml)
    slice_position_map = bmeta.get_slice_position_map_from_config(cfg)
    MimosaReader.load_correspondence_from_yaml(cfg)

    session = bm.BIDSSession(bids_root_path)

    files_to_process = []
    sessions_by_sub = {}
    samples_rows    = []

    for entry in cfg.get("samples", {}).get("entries", []):
        subject_path = entry["path"]
        subject = entry.get("subject")
        print("DEBUG YAML subject path:", subject_path)
        if not os.path.exists(subject_path):
            print(f"WARNING: path not found: {subject_path}")
            continue
        for sample in entry.get("samples", []):
            derived_from = sample.get("derived_from", "n/a")
            sample_type = sample.get("sample_type", "technical sample")
            participant_id = sample.get("participant_id", f"sub-{subject}")
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

                files_to_process.append(

                    (
                        subject_path,
                        filename,
                        derived_from,
                        sample_type,
                        participant_id,
                    ))
    for input_dir, filename, derived_from, sample_type, participant_id_from_yaml in files_to_process:
        full_input_path = os.path.join(input_dir, filename)
        czi_id = os.path.splitext(filename)[0]

        print(f"\n>>> Processing: {filename}")

        try:
            with MimosaReader(full_input_path) as reader:
                if reader is None:
                    print(f"    SKIP: cannot open {filename}")
                    continue

                summary = reader.get_summary()

                print(
                    f"    Subject: {summary['sub']}, "
                    f"Date: {summary['acq_time']}, "
                    f"Sample: {summary['sample']}"
                )

                bids_info = session.get_bids_info(
                    summary_meta=summary,
                    czi_id=czi_id,
                    section_idx=None,
                )

                participant_id = participant_id_from_yaml or f"sub-{bids_info['sub']}"

                slide_num = len([
                    r for r in samples_rows
                    if r["sample_id"].startswith("sample-slide")
                    and r["participant_id"] == participant_id
                ]) + 1

                slide_id = f"sample-slide{slide_num}"

                # Pour le nom BIDS : _sample-slide01
                # donc bids_info["sample"] = "slide01"
                bids_info["sample"] = slide_id.replace("sample-", "")

                samples_rows.append({
                    "sample_id": slide_id,
                    "participant_id": participant_id,
                    "sample_type": sample_type,
                    "anatomical_region": derived_from,
                    "source_filename": filename,
                })

                sub = bids_info["sub"]
                ses_id = f"ses-{bids_info['ses']}"
                sessions_by_sub.setdefault(sub, {})
                sessions_by_sub[sub][ses_id] = bids_info["acq_time"]

                czi.czi2bitmapHPC(
                    input_dir,
                    filename,
                    bids_root_path,
                    bids_info,
                    downsampling_factor,
                    output_format,
                    res_label=res_label,
                    reader=reader,
                    slice_position_map=slice_position_map,
                    original_thickness=args.original_thickness,
                    reorient=args.reorient,
                    block_value=args.block_value,
                    threads=args.threads,
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
            os.path.join(bids_root_path, "derivatives", "2D","downsampled"),
            sub,
            rows,
        )

    bmeta.write_samples_tsv(bids_root_path, samples_rows)

    print("\n[SUCCESS] Conversion done.")

if __name__ == "__main__":
    main()