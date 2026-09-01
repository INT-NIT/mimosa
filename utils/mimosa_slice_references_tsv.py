import json, glob, os, re, sys, numpy as np, nibabel as nb

# Build the slice reference table as a TSV:
#   subject  session  chunk  SlicePosition_mm  channels  resolutions
# One row per slice (subject, session, chunk). "channels" and "resolutions"
# list every stain and every resolution found for that slice.
#
# Usage (standalone): python mimosa_slice_references_tsv.py <bids_root> [output.tsv]
# Or import build_slice_references_tsv(bids_root, out_tsv) from another script.


def _grab(pattern, text):
    m = re.search(pattern, text)
    return m.group(1) if m else None


def _res_sort_key(r):
    m = re.match(r"(\d+)", r)
    return int(m.group(1)) if m else 0


def build_slice_references_tsv(bids_root, out_tsv=None):
    """Scan the dataset sidecars and (re)write the slice reference TSV.

    Returns the number of slices written. Safe to call again after a partial
    (-only_slices) run: it re-scans everything, so the table stays up to date.
    """
    if out_tsv is None:
        out_tsv = os.path.join(bids_root, "derivatives", "2D",
                               "mimosa_slice_references.tsv")

    # (subject, session, chunk) -> {pos, z, channels set, resolutions set}
    rows = {}
    for f in sorted(glob.glob(f"{bids_root}/**/sub-*.json", recursive=True)):
        nii = f[:-5] + ".nii.gz"
        if not os.path.exists(nii):
            continue
        meta = json.load(open(f))
        if "SlicePosition" not in meta or "NumberOfSlices" not in meta:
            continue

        name = os.path.basename(f)
        sub = _grab(r"sub-([A-Za-z0-9]+)", name) or "n/a"
        ses = _grab(r"ses-([A-Za-z0-9]+)", name) or "n/a"
        chunk = meta.get("SliceIndex")
        if chunk is None:
            chunk = _grab(r"chunk-([0-9]+)", name) or "n/a"
        stain = _grab(r"stain-([A-Za-z0-9]+)", name)
        res = _grab(r"res-([A-Za-z0-9]+)", name)

        N = int(meta["NumberOfSlices"])
        pos = int(meta["SlicePosition"])

        # thickness (mm) = largest affine column = the slice (depth) axis
        thickness = max(np.linalg.norm(nb.load(nii).affine[:3, :3], axis=0))

        # sign of Z depends on the reorientation used at stacking (read from JSON)
        reorient = (meta.get("SFormReorientationMode")
                    or meta.get("SFormVolumeReorientationMode")
                    or meta.get("VolumeReorientationMode")
                    or "none").replace(" ", "").lower()
        sign_z = -1 if ("-z" in reorient or "flip_z" in reorient) else 1

        z = round(float(sign_z * (pos - (N - 1) / 2) * thickness), 4)

        key = (sub, ses, str(chunk))
        entry = rows.setdefault(
            key, {"pos": pos, "z": z, "channels": set(), "resolutions": set()})
        if stain:
            entry["channels"].add(stain)
        if res:
            entry["resolutions"].add(res)

    # sort by subject, then session, then depth (SlicePosition)
    ordered = sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[1]["pos"]))

    os.makedirs(os.path.dirname(out_tsv), exist_ok=True)
    with open(out_tsv, "w") as out:
        out.write("subject\tsession\tchunk\tSlicePosition_mm\tchannels\tresolutions\n")
        for (sub, ses, chunk), e in ordered:
            channels = ",".join(sorted(e["channels"]))
            resolutions = ",".join(sorted(e["resolutions"], key=_res_sort_key))
            out.write(f"{sub}\t{ses}\t{chunk}\t{e['z']}\t{channels}\t{resolutions}\n")

    print("Wrote:", out_tsv, "| slices:", len(ordered))
    return len(ordered)


if __name__ == "__main__":
    _bids_root = sys.argv[1]
    _out_tsv = sys.argv[2] if len(sys.argv) > 2 else None
    build_slice_references_tsv(_bids_root, _out_tsv)
