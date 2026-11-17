import os
import sys

# Make the repo root (the folder that contains core/) importable, whatever the
# depth of this script, so "from core.bids import ..." works.
_ROOT = os.path.abspath(os.path.dirname(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.isdir(os.path.join(_ROOT, "core")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)

import argparse

from core import czi_convert as czi
from core.bids.czi_reader import MimosaReader
from core.bids import bids_manager as bm
from core.bids import bids_metadata as bmeta


def parse_slice_indices(value):
    """Parse comma/semicolon-separated slice indices."""
    if value is None:
        return None

    tokens = [
        token.strip()
        for token in str(value).replace(";", ",").split(",")
        if token.strip()
    ]
    if not tokens:
        raise argparse.ArgumentTypeError(
            "-only_slices must contain at least one slice index, e.g. 60,62,63"
        )

    try:
        indices = {int(token) for token in tokens}
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Slice indices must be integers, e.g. 60,62,63"
        ) from exc

    if any(index < 0 for index in indices):
        raise argparse.ArgumentTypeError("Slice indices must be non-negative")

    return indices


def main():
    parser = argparse.ArgumentParser(description="Process for CZI conversion to BIDS")
    parser.add_argument(
        "-f", "--output_format", type=str, required=True,
        help="tif, nii or both",
    )
    parser.add_argument(
        "-df", "--downsampling_factor", type=str, required=True,
        help=(
            "Downsampling exponent(s), factor = 2**exponent. "
            "Accepts a single value (e.g. 4) or a comma separated list "
            "(e.g. 4,6,8). Several resolutions cost one single native read."
        ),
    )
    parser.add_argument(
        "-o", "--output_path", type=str, required=True,
        help="BIDS dataset root",
    )
    parser.add_argument(
        "-y", "--yaml", type=str, default="metadata.yml",
        help="metadata YAML file",
    )
    parser.add_argument(
        "-original_thickness", required=False, type=float, default=100,
        help="Histological section thickness in micrometers",
    )
    parser.add_argument(
        "-reorient", type=str, required=False, default="none",
        help="Reference reorientation used to compute SFormMatrix for 2D slices",
    )
    parser.add_argument(
        "-only_slices", type=str, default=None,
        help=(
            "Process only these slice indices (comma separated, e.g. 60,62,63). "
            "The total slice count and positions are still computed from the "
            "complete slice list in the YAML."
        ),
    )
    parser.add_argument(
        "-delete", "--delete-content", dest="delete_content",
        action="store_true",
        help=(
            "Replace the pixel/voxel data of the selected slices with zeros. "
            "Requires -only_slices. Files are kept and their JSON sidecars are "
            "marked with DeleteContent=true and DeleteContentMethod=zero_fill."
        ),
    )
    parser.add_argument(
        "-refreeze", action="store_true",
        help=(
            "Recompute and overwrite the frozen slice total (NumberOfSlices) "
            "stored in the YAML, from the current slice list."
        ),
    )
    parser.add_argument(
        "-subject", dest="subject", type=str, default=None,
        help=(
            "Convert only this subject (the 'subject' value in the YAML). "
            "Omit to convert every subject."
        ),
    )

    args = parser.parse_args()

    only_slices = parse_slice_indices(args.only_slices)
    if args.delete_content and only_slices is None:
        parser.error("-delete requires -only_slices to avoid zeroing every slice")

    output_format = args.output_format.lower().strip()
    if output_format not in ("tif", "nii", "both"):
        parser.error("output_format must be 'tif', 'nii' or 'both'")

    clean_output_path = args.output_path.rstrip("/")

    try:
        downsampling_factor = sorted({
            int(token)
            for token in str(args.downsampling_factor).replace(";", ",").split(",")
            if token.strip()
        })
    except ValueError as exc:
        parser.error(f"Invalid downsampling exponent: {exc}")

    if not downsampling_factor:
        parser.error("At least one downsampling exponent is required")

    res_label = {exponent: f"{exponent}x" for exponent in downsampling_factor}
    print("Exported resolutions:", ", ".join(res_label.values()))
    print("Reduction method    : zoom (ZEN pyramid)")
    if args.delete_content:
        print("DELETE CONTENT      : selected slices will be written as zeros")
        print("Selected slices     :", ", ".join(map(str, sorted(only_slices))))

    bids_root_path = bm.initialize_dataset(
        clean_output_path,
        yaml_path=args.yaml,
        output_format=output_format,
    )
    cfg = bmeta.load_metadata_config(args.yaml)
    bmeta.update_yaml_with_slices(args.yaml)
    cfg = bmeta.load_metadata_config(args.yaml)

    # Compute positions from the complete slice list, not only the selected
    # slices. This preserves the true depth of each selected slice.
    slice_maps_by_subject = {}
    for entry in cfg.get("samples", {}).get("entries", []):
        subj = entry.get("subject")
        if subj is None or subj in slice_maps_by_subject:
            continue
        if args.subject and str(subj) != str(args.subject):
            continue

        slice_maps_by_subject[subj] = bmeta.load_or_freeze_slice_reference_in_yaml(
            cfg=cfg,
            yaml_path=args.yaml,
            subject=subj,
            slice_indices=bmeta._all_slice_indices(cfg, subject=subj),
            refreeze=args.refreeze,
        )

    MimosaReader.load_correspondence_from_yaml(cfg)

    # Number sessions by real acquisition date (earliest day = ses-01).
    bm.build_session_order_from_acq_time(cfg, bids_root_path)
    session = bm.BIDSSession(bids_root_path)

    files_to_process = []
    sessions_by_sub = {}
    samples_rows = []

    for entry in cfg.get("samples", {}).get("entries", []):
        subject_path = entry["path"]
        subject = entry.get("subject")

        if args.subject and str(subject) != str(args.subject):
            continue
        if not os.path.exists(subject_path):
            print(f"WARNING: path not found: {subject_path}")
            continue

        for sample in entry.get("samples", []):
            sample_type = sample.get("sample_type", "technical sample")
            participant_id = sample.get("participant_id", f"sub-{subject}")

            for file_entry in sample.get("files", []):
                filename = file_entry.get("filename")
                slices = file_entry.get("slices", [])

                if not filename or not filename.endswith(".czi"):
                    continue
                if not slices:
                    print(f"  SKIP YAML file without slices: {filename}")
                    continue

                full_path = os.path.join(subject_path, filename)
                if not os.path.exists(full_path):
                    print(f"WARNING: file listed in YAML but not found: {full_path}")
                    continue

                files_to_process.append((
                    subject_path,
                    filename,
                    sample_type,
                    participant_id,
                    subject,
                ))

    subjects_copied = set()

    for input_dir, filename, sample_type, participant_id_from_yaml, subject_label in files_to_process:
        full_input_path = os.path.join(input_dir, filename)
        czi_id = os.path.splitext(filename)[0]
        is_first = subject_label not in subjects_copied
        bm.create_sourcedata_links(
            full_input_path, subject_label, bids_root_path, copy_real=is_first
        )
        subjects_copied.add(subject_label)
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

                participant_id = (
                    participant_id_from_yaml or f"sub-{bids_info['sub']}"
                )
                slide_num = len([
                    row for row in samples_rows
                    if row["sample_id"].startswith("sample-slide")
                    and row["participant_id"] == participant_id
                ]) + 1
                slide_id = f"sample-slide{slide_num}"
                bids_info["sample"] = slide_id.replace("sample-", "")

                samples_rows.append({
                    "sample_id": slide_id,
                    "participant_id": participant_id,
                    "sample_type": sample_type,
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
                    slice_position_map=slice_maps_by_subject[subject_label],
                    original_thickness=args.original_thickness,
                    reorient=args.reorient,
                    only_slices=only_slices,
                    delete_content=args.delete_content,
                )

        except Exception as exc:
            print(f"    ERROR processing {filename}: {exc}")
            continue

    for sub, session_dates in sessions_by_sub.items():
        rows = [
            {"session_id": ses_id, "acq_time": session_dates[ses_id]}
            for ses_id in sorted(session_dates)
        ]
        bmeta.write_subject_sessions_tsv(
            os.path.join(bids_root_path, "derivatives", "2D", "downsampled"),
            sub,
            rows,
        )

    bmeta.write_samples_tsv(bids_root_path, samples_rows)

    ref_tsv = os.path.join(
        bids_root_path, "derivatives", "2D", "mimosa_slice_references.tsv"
    )
    if os.path.exists(ref_tsv):
        try:
            from utils.mimosa_slice_references_tsv import build_slice_references_tsv
            build_slice_references_tsv(bids_root_path, ref_tsv)
            print(f"Slice reference table updated: {ref_tsv}")
        except Exception as exc:
            print(f"WARNING: could not update slice reference table: {exc}")

    print("\n[SUCCESS] Conversion done.")


if __name__ == "__main__":
    main()
