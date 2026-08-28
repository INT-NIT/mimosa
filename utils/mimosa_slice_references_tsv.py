import json, glob, os, re, sys, numpy as np, nibabel as nb

# Build the slice reference table as a TSV:
#   subject  NumberOfSlices  SliceIndex  SlicePosition  Z_mm  path
# One row per slice. The path contains the session (ses-XX) and the chunk
# (chunk-XXX), so it is clear which session each slice belongs to.
#
# Usage: python mimosa_slice_references_tsv.py <bids_root> [output.tsv]

bids_root = sys.argv[1]
out_tsv = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
    bids_root, "derivatives", "2D", "mimosa_slice_references.tsv")

seen = {}  # (subject, SlicePosition) -> row  (one row per slice)
for f in sorted(glob.glob(f"{bids_root}/**/sub-*.json", recursive=True)):
    nii = f[:-5] + ".nii.gz"
    if not os.path.exists(nii):
        continue
    meta = json.load(open(f))
    if "SlicePosition" not in meta or "NumberOfSlices" not in meta:
        continue

    name = os.path.basename(f)
    m = re.search(r"sub-([A-Za-z0-9]+)", name)
    sub = m.group(1) if m else "n/a"

    N = int(meta["NumberOfSlices"])
    pos = int(meta["SlicePosition"])
    idx = meta.get("SliceIndex", "n/a")

    # thickness (mm) = largest affine column = the slice (depth) axis
    thickness = max(np.linalg.norm(nb.load(nii).affine[:3, :3], axis=0))

    # sign of Z depends on the reorientation used at stacking (read from JSON)
    reorient = (meta.get("SFormReorientationMode")
                or meta.get("SFormVolumeReorientationMode")
                or meta.get("VolumeReorientationMode")
                or "none").replace(" ", "").lower()
    sign_z = -1 if ("-z" in reorient or "flip_z" in reorient) else 1

    z = round(float(sign_z * (pos - (N - 1) / 2) * thickness), 4)

    rel = os.path.relpath(nii, bids_root)
    seen.setdefault((sub, pos), (sub, N, idx, pos, z, rel))  # keep the first seen

rows = sorted(seen.values(), key=lambda r: (r[0], r[3]))  # sort by subject, then position

os.makedirs(os.path.dirname(out_tsv), exist_ok=True)
with open(out_tsv, "w") as out:
    out.write("subject\tNumberOfSlices\tSliceIndex\tSlicePosition\tZ_mm\tpath\n")
    for r in rows:
        out.write("\t".join(str(x) for x in r) + "\n")

print("Wrote:", out_tsv, "| slices:", len(rows))
