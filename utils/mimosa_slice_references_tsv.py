import json, glob, os, re, sys, numpy as np, nibabel as nb

# Build the slice reference table as a TSV:
#   subject  NumberOfSlices  SliceIndex  Z_mm  path
# One row per slice. The path is truncated to the session folder (ses-XX); the
# chunk is already given by the SliceIndex column.
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

    # Path only up to the session folder (ses-XX): the chunk is already given by
    # the SliceIndex column, so the full filename is not needed in the table.
    rel = os.path.relpath(nii, bids_root)
    parts = rel.split(os.sep)
    ses_i = next((i for i, p in enumerate(parts) if p.startswith("ses-")), None)
    rel = os.sep.join(parts[:ses_i + 1]) if ses_i is not None else os.path.dirname(rel)

    # pos is kept only to sort/deduplicate; it is not written to the table.
    seen.setdefault((sub, pos), (pos, sub, N, idx, z, rel))  # keep the first seen

rows = sorted(seen.values(), key=lambda r: (r[1], r[0]))  # sort by subject, then position

os.makedirs(os.path.dirname(out_tsv), exist_ok=True)
with open(out_tsv, "w") as out:
    out.write("subject\tNumberOfSlices\tSliceIndex\tZ_mm\tpath\n")
    for r in rows:
        out.write("\t".join(str(x) for x in r[1:]) + "\n")  # r[0] (pos) is only for sorting

print("Wrote:", out_tsv, "| slices:", len(rows))
