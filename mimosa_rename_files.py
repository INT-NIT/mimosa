import os
import argparse
import shutil

import numpy as np
import subprocess as sp
import nibabel as nb

# Folder containing the input czi data
input_path='/tmp'
def dir_path(path):
    if os.path.isdir(path):
        return path
    else:
        raise argparse.ArgumentTypeError(f"readable_dir:{path} is not a valid path")
def main():
    parser = argparse.ArgumentParser(description='Process for CZI concersion to BIDS')
    parser.add_argument('-i', '--input_path', type=dir_path, help='root path containing all .czi files')
    parser.add_argument('-df', '--downsampling_factor', type=int)
    parser.add_argument("--test", action="store_true", help="normalize signal robust [min,max] -> [0,255]")

    args = parser.parse_args()

    downsampling_factor = 4

    input_path=dir_path(args.input_path)
    output_path = args.output_path

    if args.downsampling_factor is not None:
        downsampling_factor = args.downsampling_factor

    print("PATH IN:",input_path)
    print("downsampling factor:",downsampling_factor)

    dirFiles = os.listdir(input_path)  # list of directory files
    # parse folder and replace prefix format by %03d for sort
    extensions = ('.tiff')
    for files in dirFiles:
        if extensions in files:
            split_files = files.split("_")
            split_S = split_files[len(split_files)-2].split("S")

            index_scene=(int(split_S[1]))

            val_index_from_S=split_files[index_scene + 2].zfill(3)

            motif="ds"+str(downsampling_factor)
            
            if (val_index_from_S!=motif):
                new_files = split_files[0].zfill(3) + "-" + split_files[index_scene + 2].zfill(3)   + "-" + split_files[len(split_files)-1]   
                if args.test:
                    print(files," ->" , new_files)
                else:
                    prtin("coucou")
                    #shutil.move(input_path + '/' + files, input_path + '/' + new_files)

if __name__ == "__main__":
    main()
