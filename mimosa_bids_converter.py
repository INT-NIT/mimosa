import argparse
import os
from python_scripts import czi_convert as czi

# Folder containing the input czi data
input_path='/tmp'
output_format='nii'
tile_number=6
downsampling_factor=4
mosaic_patch_size=1536

def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")
def main():
    parser = argparse.ArgumentParser(description='Process for CZI concersion to BIDS')
    parser.add_argument('-i', '--input_path', type=dir_path, help='root path containing all .czi files')
    parser.add_argument('-f', '--output_format', type=str, required=True, help='output format TIFF or nii format (default: nii)')
    parser.add_argument('-t', '--tile_number', type=int, required=True,help='number of tile for a single square mosaic patch (NxN, default: N=6)')
    parser.add_argument('-df', '--downsampling_factor', type=int, required=True, help=' factor N for downsampling (default: N=4 (=2^4)=16): 256x256 -> 16x16')
    parser.add_argument('-sms', '--single_mosaic_size', type=int, help='default: 1536')
    parser.add_argument('-o', '--output_path', type=str, help='output path (default: input_path/czi2XXX, with XXX=format')

    args = parser.parse_args()

    input_path=dir_path(args.input_path)
    output_format=args.output_format
    tile_number=args.tile_number
    downsampling_factor=(args.downsampling_factor)**2

    if args.output_path is not None:
        output_path = dir_path(args.output_path)
    else:
        output_path = input_path+"/czi2" + output_format

    print("PATH IN:",input_path)
    print("tile_number:",tile_number)
    print("downsampling factor:",downsampling_factor)

    # Check if the directory exists
    if not os.path.exists(output_path):
        os.mkdir(output_path)
        print("PATH OUT '% s' created" % output_path)
    else:
        print("PATH OUT '% s' not created (already exists)" % output_path)

    print("OUTPUT FORMAT:", output_format)

    extensions = ('.czi')

    czifilelist = []
    for root, dirs, files in os.walk(input_path):
        for file in files:
            if file.endswith(extensions):
                czifilelist.append(file)

    #czi.czi2bitmap(input_path, file, output_path, tile_number, downsampling_factor, mosaic_patch_size, output_format)
    print(len(czifilelist))

    for csifileindex in range(0,len(czifilelist)):
        print(czifilelist[csifileindex])
        czi.czi2bitmap(input_path, czifilelist[csifileindex], output_path, tile_number, downsampling_factor, mosaic_patch_size, output_format)

    print("done")

if __name__ == "__main__":
    main()
