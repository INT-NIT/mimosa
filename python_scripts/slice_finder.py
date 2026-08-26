import json, glob, sys, numpy as np, nibabel as nb
 
bids_root, sub, z = sys.argv[1], sys.argv[2], float(sys.argv[3])
 
files = glob.glob(f"{bids_root}/**/sub-{sub}*.json", recursive=True)
 
# N and thickness (mm) read from one slice
meta0 = json.load(open(files[0]))
N = int(meta0["NumberOfSlices"])
thickness = max(np.linalg.norm(nb.load(files[0][:-5] + ".nii.gz").affine[:3, :3], axis=0))
 
# Z (mm) -> SlicePosition :  k = z / thickness + (N-1)/2
k = round((N - 1) / 2 - z / thickness) 
for f in files:
    meta = json.load(open(f))
    if meta.get("SlicePosition") == k:
        print("SliceIndex:", meta.get("SliceIndex"))
        print("Path:", f[:-5] + ".nii.gz")
        break
 