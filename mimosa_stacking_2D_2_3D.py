import os
import argparse
import shutil
import re 
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
    parser.add_argument('-df', '--downsampling_factor', type=int, help=' factor N for downsampling (default: N=4 (=2^4)=16): 256x256 -> 16x16')
    parser.add_argument('-ps', '--padding_size', type=int, help=' size of padding (in pixels), default = 100')
    parser.add_argument("--norm", action="store_true", help="normalize signal robust [min,max] -> [0,255]")
    parser.add_argument("--denoise", action="store_true", help="Denoise image using NLM from Ants Library")
    parser.add_argument('-o', '--output_path', type=str, help='output path (default: input_path/preproc')

    args = parser.parse_args()

    downsampling_factor = 64
    original_res = 0.0003249
    #original_thickness = 0.400
    original_thickness = 0.100
    
    padding_size = 100

    input_path=dir_path(args.input_path)
    output_path = args.output_path

    if args.downsampling_factor is not None:
        downsampling_factor = 2 ** (args.downsampling_factor)

    if args.padding_size is not None:
        padding_size=args.padding_size

    if args.norm:
        print("Normalization is enabled")

    if not os.path.exists(output_path):
        os.mkdir(output_path)
        print("PATH OUT '% s' not created (already exists)" % output_path)

    print("PATH IN:",input_path)
    print("downsampling factor:",downsampling_factor)

    #if args.denoise:
    #    print("Denoising is enabled")

    dirFiles = os.listdir(input_path)  # list of directory files
    # parse folder and replace prefix format by %03d for sort

    # create a regex to be able to analyse any format with - or _ 
    pattern = re.compile(
    r'(?P<sub>[A-Za-z0-9]+)[-_]'
    r'(?P<sample>[A-Za-z0-9]+)[-_]'
    r'(?P<scenes>[0-9\-_]+)[-_]'
    r'ds(?P<ds>\d+)[-_]'
    r'S(?P<S>\d+)[-_]'
    r'C(?P<C>\d+)'
    )

    extensions = ('.nii.gz')
    for files in dirFiles:
        if extensions in files:
            match = pattern.search(files)
            if match :
                sub = match.group("sub")
                scenes_raw = match.group("scenes")
                scenes_list = [int(x) for x in re.split(r"[-_]", scenes_raw)]

                S_index = int(match.group("S"))
                scene_value = scenes_list[S_index]
                C = "C" + match.group("C")
                
                new_name = f"{sub}-{scene_value}-{C}.nii.gz"

                shutil.copyfile(input_path + '/' + files, output_path + '/' + new_name)

    dirFiles = os.listdir(output_path)  # list of directory files


    detected_channels=set()
    for files in dirFiles:
        if '.nii.gz' in files:
            match = re.search(r'C(\d+)', files)   # search the pattern C followed by a number  in files       
            if match: # match = object which contains <re.Match object; span=(6, 8), match='C1'>
                channel = match.group(0) # get C1 
                detected_channels.add(channel)
    detected_channels = sorted(list(detected_channels))
    print(f"Detected channels: {detected_channels}") 
    

    for channel in detected_channels:
        myimages_channel = []  # list of image filenames
        for files in dirFiles:  # filter out all non jpgs
            if channel+'.nii.gz' in files:
                myimages_channel.append(files)

        myimages_channel_sorted = sorted(myimages_channel)  # sort numerically in ascending order
        print(f"Number of images per channel  {channel}: {len(myimages_channel_sorted)}")



        list_w = []
        list_h = []"Width": w_downsampled,
            "Height": h_downsampled

        for i in range(0, len(myimages_channel_sorted) ):
            rawImage = output_path + "/" + myimages_channel_sorted[i]
            rawImage_nii = nb.load(rawImage)
            list_w.append(rawImage_nii.shape[0])
            list_h.append(rawImage_nii.shape[1])

        max_w = np.max(list_w)
        max_w_index = list_w.index(max_w)
        max_h = np.max(list_h)
        max_h_index = list_h.index(max_h)
        print(max_w, max_w_index, max_h, max_h_index)
        padding_target_shape = np.array((padding_size + max_w, padding_size + max_h, len(myimages_channel_sorted)))
        print(padding_target_shape)

        downsampled_res = original_res * downsampling_factor
        new_resolution = [downsampled_res, downsampled_res, original_thickness]
        new_affine = np.zeros((4, 4))
        new_affine[:3, :3] = np.diag(new_resolution)
        new_affine[:3, 3] = padding_target_shape * new_resolution / 2. * -1
        new_affine[3, 3] = 1.
        stack_of_slices = np.zeros((padding_target_shape[0], padding_target_shape[1], padding_target_shape[2]))
        stack_id = 0

        print(len(myimages_channel_sorted))


        for i in range(0, len(myimages_channel_sorted)):
            rawImage = output_path + "/" + myimages_channel_sorted[i]

            array_img = nb.load(rawImage)
            image_data = array_img.get_fdata()

            image_data_arr = np.asarray(image_data)
            image_data_norm = (255 * (image_data_arr - np.percentile(image_data_arr, 5)) / np.percentile(image_data_arr, 95)).astype(int)

            image_data_norm_2D = np.squeeze(image_data_norm, 2)

            shift_x = (padding_target_shape[0] - array_img.shape[0])
            shift_y = (padding_target_shape[1] - array_img.shape[1])

            print(i, round(shift_x), round(shift_y))
            print (rawImage,image_data_norm_2D.shape)
            print((round(shift_x / 2), shift_x - round(shift_x / 2)), (round(shift_y / 2), shift_y - round(shift_y / 2)))
            image_data_norm_arr_padded = np.pad(image_data_norm_2D, \
                                            ((round(shift_x / 2), shift_x - round(shift_x / 2)), (round(shift_y / 2), shift_y - round(shift_y / 2))),\
                                            'constant', constant_values=(0))

            stack_of_slices[:, :, stack_id] = image_data_norm_arr_padded[:, :]
            stack_id = stack_id + 1

        empty_header = nb.Nifti1Header()
        empty_header.get_data_shape()

        img = nb.Nifti1Image(stack_of_slices, new_affine, empty_header)

        path3D = output_path + "/" + f"slice3D_{channel}.nii.gz"
        nb.save(img, path3D)




    # if args.denoise:
    #     print("Denoising is enabled")
    #
    # for i in range(0, len(myimages) - 1):
    #     rawImage = PATH_nii + myimages[i]
    #     normImage = pathNorm + "image_" + str(i).zfill(2) + ".nii.gz"









if __name__ == "__main__":
    main()