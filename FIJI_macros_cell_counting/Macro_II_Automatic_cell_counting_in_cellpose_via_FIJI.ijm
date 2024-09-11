//Macro II Creating selections for cell counting. MIMOSA Project. INT. 2024
//This macro counts cells in the previously defined ROIs in the images (2D brain slices) contained in the folder.
//It requires a folder containing all the images to be analyzed, and the previously created selections (ROIs) with MacroI. Images have to be 1 channel .tiff format. Minimal modifications are required to process multichannel (composite) images.
//If images are .tif, replace the extension .tiff by .tif (or other) where corresponds.
//Input approx diameter in pixels of your cells in the line "diam = 14" if needed. If you need to change cellpose parameters read the docs here (https://cellpose.readthedocs.io/en/latest/settings.html#settings) and change them in the specific line (Step 5).
//This macro requires a Cellpose environment installed in your computer. Check info in https://github.com/MouseLand/cellpose.
//This macro requires PTBIOP plugins in FIJI (https://wiki-biop.epfl.ch/en/ipa/fiji/update-site) and a correct setting-up of the Cellpose FIJI wrapper (https://github.com/BIOP/ijl-utilities-wrappers).
//This macro also uses SCF plugins (https://github.com/mpicbg-scicomp/Interactive-H-Watershed) to convert label images to ROI manager particles.
//After completion, a folder called /Cells_and_CP_masks_def/ will be created in the parent folder. This contains original images and label images that can be further refined in cellpose for accuracy or for training your own cellpose model afterwards. 
//The minimal size for a cell is recommended to be around 10 pixels. Bigger cell size (in pixels) increase performance and detection capabilities of cellpose.
//To deal with the problem exemplified here https://forum.image.sc/t/cellpose-missing-most-cells-in-sparsely-populated-image/76444 and here https://forum.image.sc/t/normalization-cellpose-fiji-wrapper/95542, out-of-the-ROI pixels are set to value=255.


// Step 1 Manages main directory and creates subdirectories.

dir1 = getDirectory("Open Folder");
list = getFileList(dir1);
dir2 = dir1 + "/selections/";
dir3 = dir1 + "/Cells_and_CP_masks/";
File.makeDirectory(dir3);
dir4 = dir1 + "/Cells_and_CP_masks_def/";
File.makeDirectory(dir4);
dir5 = dir1 + "/CP_inputs/";
File.makeDirectory(dir5);
dir6 = dir1 + "/ROI_sets/";
File.makeDirectory(dir6);
list = Array.sort(list); 

diam = 14; // Think about including in box for user to select.... Diameter for cellpose automatic analysis. Needed to be changed if different resolutions are used
run("Set Measurements...", "area centroid shape redirect=None decimal=2");

// Step 2 Iterates over files in main directory and creates reduced CP inputs and a transient version of "cells" in dir3.

for (i = 0; i < list.length; i++) {
    if (endsWith(list[i], ".tiff")) {//Change extension if your images are .tif or other format
        open(dir1 + list[i]);
        img_name = getTitle();
        filename_clean = File.nameWithoutExtension();
        source_info = getInfo("image.filename");
        getDimensions(width, height, channels, slices, frames);
        w = width;
        h = height;
        saveAs("Tiff", dir3 + filename_clean + "_cells");
        img_name_cells=getTitle();
        cells = dir3 + filename_clean + "_cells.tif";
        
        // Step 3 Looks for selections matching filenames in dir2, this directory was created in the previous macro and contains selections as .rois.
        
        list_b = getFileList(dir2);
        list_b = Array.sort(list_b);
        for (j = 0; j < list_b.length; j++) {
            if (matches(list_b[j], "^sel_" + filename_clean + ".roi$")){//Opens selection matching the filename created in previous macro
                open(dir2 + list_b[j]);
        
        
        // Step 4 Stores selections and creates CP inputs.
        
        getSelectionCoordinates(x, y); // These are the ones for the GLOBAL VERSION of the image
        x_sel = x;
        y_sel = y;        
        run("Crop");////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
        setBackgroundColor(255, 255, 255);////////////////This is my humble way of dealing with the normalization of cellpose. Newer versions of CP allow to control this even from the GUI. ///////////////////////
        run("Clear Outside");/////////////////////////////However you cannot pass this argument to the FIJI wraper of cellpose, and this is the reason why I do this. It's dirty, I know, but it works./////////////
        run("Add Specified Noise...", "standard=5");////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
        saveAs("Tiff", dir5 + filename_clean + "_CP_input");
        CPI=dir5 + filename_clean + "_CP_input.tif";
        CP_input = getTitle();
        getSelectionCoordinates(x, y); // These are the ones for the REDUCED VERSION of the image, so the CP inputs
        x_sel_red = x;
        y_sel_red = y;
        time = getTime();
        
        // Step 5 Starts processing in cellpose with FIXED parameters cellproba_threshold=-6.0 flow_threshold=0.9; diameter is fixed to 7 pixels. PTPBIOP Cellpose wraper for FIJI and SCF plugins installed are necesary for this step.
        
        newImage("Labels", "32-bit black", w, h, 1);
        labels = getTitle();
        setTool("polygon");
        for (k = 0; k < x_sel.length; k++) {
            makeSelection("polygon", x_sel, y_sel);
        }
        
        selectImage(CP_input);
        
        //Cellpose arguments are contained in the line below. Consider testing one image per series to modify accordingly. Also consider changing for the site of injection and use unique parameters for that slice. Also, modify cellpose parameters here if needed.

        run("Cellpose Advanced", "diameter=" + diam + " cellproba_threshold=-6.0 flow_threshold=0.9 anisotropy=1.0 diam_threshold=12.0 model=cyto nuclei_channel=0 cyto_channel=1 dimensionmode=2D stitch_threshold=-1.0 omni=false cluster=false additional_flags=");
        cp_mask = getTitle();
        selectImage(cp_mask);
        setTool("polygon");
        for (k = 0; k < x_sel_red.length; k++) {
            makeSelection("polygon", x_sel_red, y_sel_red);
        }
        run("Copy");
        selectImage(labels);
        run("Paste");
        selectImage(labels);
        saveAs("Tiff", dir3 + filename_clean + "_CP_TH_minus_6_F_TH_09_labels");
        img_lab_clean_a = filename_clean + "_CP_TH_minus_6_F_TH_09_labels";
        run("Select None");//Ensures no selection remaining, otherwise the following could crash
        run("LabelMap to ROI Manager (2D)");
        
        
// Step 6 Processes particles of ROI manager and excludes by area and circularity.

n = roiManager("count");
if (n != 0) {
	
    // Step 6.1 ROIs loop to exclude elongated particles.
    
    minimum_circ = 0.5;//I have chosen this value, but it may be changed based on user experience over different datasets. To be determined.
    
    minimum_size = 90;//Given the structure of this script, this is in PIXELS!!. Consider to scale the labels image according to the initial one and change this to units (microns) if it helps. Change if different resolutions are used.

    n = roiManager("count");
    to_be_deleted_circ = newArray(); // Renamed array for circ exclusion

    for (k = 0; k < n; k++) {
        run("Clear Results"); // Ensure Results window is empty for each new ROI
        roiManager("select", k);
        roiManager("Measure");

        // Get the circularity value from the Results window for each ROI
        
        Circ_to_remove = getResult("Circ."); // Get the value from the Result window

        if (Circ_to_remove < minimum_circ) {
            to_be_deleted_circ = Array.concat(to_be_deleted_circ, k);
        }
    }

    if (to_be_deleted_circ.length > 0) {
        roiManager("Select", to_be_deleted_circ);
        roiManager("Delete");
    }

    // This section avoids ROI manager bugs. Is dirty, but it is like this
    run("Select None");
    close("Results");
    roiManager("Deselect");
    roiManager("Show All");
    roiManager("Show None");
    // This section avoids ROI manager bugs. Is dirty, but it is like this

    // Step 6.2 ROIs loop to exclude by area.
    
    n_b = roiManager("count");
    to_be_deleted_area = newArray(); // Renamed array for area exclusion

    for (l = 0; l < n_b; l++) {
        run("Clear Results"); // Ensure Results window is empty for each new ROI
        roiManager("select", l);
        roiManager("Measure");

        // Get the area value from the Results window for each ROI
        
        Area_to_remove = getResult("Area"); // Get the value from the Result window

        if (Area_to_remove < minimum_size) {
            to_be_deleted_area = Array.concat(to_be_deleted_area, l);
        }
    }

    if (to_be_deleted_area.length > 0) {
        roiManager("Select", to_be_deleted_area);
        roiManager("Delete");
    }
}
		
		// Step 7 Saves final ROI manager without the previously excluded particles.
		
        n_fin = roiManager("count");
        if (n_fin != 0) {
            roiManager("Save", dir6 + filename_clean + "_RoiSet_CP_TH_minus_6_F_TH_09.zip");
            ROIS_a = dir6 + filename_clean + "_RoiSet_CP_TH_minus_6_F_TH_09.zip";
        } else {
            print("No ROIset saved in " + filename_clean + "_CP_TH_minus_6_F_TH_09.zip");
        }
        
        close("*");
        close("Results");
        close("ROI Manager");
		
		
		//Step 8 Generates final 16-bits Cellpose inputs for human analysis based on filtered ROIsets. SCF plugins installed in FIJI are necesary for this step.
		
        open(cells);
        run("Select None");
        saveAs("Tiff", dir4 + filename_clean + "_cells");
        open(ROIS_a);
        newImage("Masks", "16-bit black", w, h, 1);
        run("ROI Manager to LabelMap(2D)");
		run("glasbey on dark");
		saveAs("Tiff", dir4 + filename_clean + "_cells_masks");
        close("*");
        close("Results");
        close("ROI Manager");
        print(img_lab_clean_a+" 1st round completed in "+(getTime()-time)+" msec");//Verbose follow up of the whole process indicating time spent per processed slice in ms.
		beep();
		}

	else {}
}
//close("*");
close(img_name_cells);
}
}
// Step cleaning 1 Erases xxxxx_cells from dir3 to reduce storage space at the end

list_dir3 = getFileList(dir3);
for (i = 0; i < list_dir3.length; i++) {
	if (!matches(list_dir3[i], ".*labels.*")) {
        File.delete(dir3 + list_dir3[i]);
    }
}

// Step cleaning 2 Erases "original" images since now they are in the Cellpose folder. Ask for this maybe is better to preserve them

list = getFileList(dir1);
list = Array.sort(list);
for (i = 0; i < list.length; i++) {
    if (endsWith(list[i], ".tif")) {
    	File.delete(dir1 + list[i]);
    }
}
