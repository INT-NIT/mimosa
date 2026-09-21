import json, glob, os, re, sys, numpy as np, nibabel as nb
 
# Repo root importable so "from core.bids import ..." works whatever the depth.
_ROOT = os.path.abspath(os.path.dirname(__file__))
while _ROOT != os.path.dirname(_ROOT) and not os.path.isdir(os.path.join(_ROOT, "core")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
 
from core.bids import bids_metadata as bmeta
 
# Build the slice reference table as a TSV:
#   subject  session  chunk  SlicePosition_mm  channels  resolutions
#
# SlicePosition_mm is computed FROM THE ACTUAL VOLUME AFFINE (the same one
# FSLeyes reads), so the table always matches what you see in FSLeyes for
# that slice in the stacked volume. No independent formula, no sign guessing.
#
# Usage: python mimosa_slice_references_tsv.py <bids_root> [output.tsv]
 
 
def _grab(pattern, text):
    m = re.search(pattern, text)
    return m.group(1) if m else None
 
 
def _res_sort_key(r):
    m = re.match(r"(\d+)", r)
    return int(m.group(1)) if m else 0
 
 
# subject -> {"affine": 4x4 np.ndarray, "reorient": str} (cached, one per subject)
_VOLUME_CACHE = {}
 
 
def _load_volume_geometry(bids_root, sub):
    """Find one stacked volume for this subject and return its affine + reorient.
 
    Depth placement (through-plane z) is identical across channels and
    resolutions for a given subject, so any one volume is enough.
    Returns None if no volume was built yet (fall back to the formula).
    """
    if sub in _VOLUME_CACHE:
        return _VOLUME_CACHE[sub]
 
    pattern = os.path.join(
        bids_root, "derivatives", "3D", "stacking",
        f"sub-{sub}", "micr", "res-*", f"sub-{sub}_*_volume.json",
    )
    geom = None
    for vj in sorted(glob.glob(pattern)):
        try:
            vmeta = json.load(open(vj))
            affine = np.array(vmeta["AffineMatrix"], dtype=float)
            reorient = (vmeta.get("VolumeReorientationMode") or "none")
            geom = {"affine": affine, "reorient": reorient}
            break
        except Exception:
            continue
 
    _VOLUME_CACHE[sub] = geom
    return geom
 
 
def _fsleyes_through_plane_z(vol_affine, reorient, N, pos):
    """World through-plane coordinate FSLeyes shows for slice `pos` in the volume.
 
    Reproduces exactly how the stacking placed the slice:
      - the depth axis starts as voxel axis 2 (width, height, nb_slices);
      - reorient may transpose it to a new axis d and flip it;
      - the volume affine maps that voxel to world; we read the dominant
        world component of column d.
    """
    if bmeta.is_identity_reorientation(reorient):
        d = 2
        flipped = False
    else:
        transpose_axes, flip_axes = bmeta.parse_reorientation_mode(reorient)
        d = list(transpose_axes).index(2)      # where the old depth axis (2) went
        flipped = d in set(flip_axes)
 
    k = (N - 1 - pos) if flipped else pos      # voxel index along the depth axis
    col = np.asarray(vol_affine, dtype=float)[:3, d]
    axis = int(np.argmax(np.abs(col)))         # dominant world axis of that column
    origin = np.asarray(vol_affine, dtype=float)[:3, 3]
    return float(col[axis] * k + origin[axis])
 
 
def build_slice_references_tsv(bids_root, out_tsv=None):
    """Scan the dataset sidecars and (re)write the slice reference TSV."""
    if out_tsv is None:
        out_tsv = os.path.join(bids_root, "derivatives", "2D",
                               "mimosa_slice_references.tsv")
 
    _VOLUME_CACHE.clear()
 
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
 
        geom = _load_volume_geometry(bids_root, sub)
        if geom is not None:
            # Exactly what FSLeyes shows for this slice in the volume.
            z = _fsleyes_through_plane_z(geom["affine"], geom["reorient"], N, pos)
        else:
            # No volume built yet: fall back to the formula (magnitude only,
            # sign from the slice's own reorient tag).
            thickness = max(np.linalg.norm(nb.load(nii).affine[:3, :3], axis=0))
            reorient = (meta.get("SFormReorientationMode")
                        or meta.get("SFormVolumeReorientationMode")
                        or meta.get("VolumeReorientationMode")
                        or "none").replace(" ", "").lower()
            sign_z = -1 if ("-z" in reorient or "flip_z" in reorient) else 1
            z = round(sign_z * (pos - (N - 1) / 2) * thickness)
 
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
 
