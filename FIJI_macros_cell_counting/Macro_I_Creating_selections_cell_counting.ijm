//Macro I Creating selections for cell counting. MIMOSA Project. INT. 2024
//This macro iterates through all files in a folder (seriated 2D slices of a brain with labelled cells) and asks the user to create selections (ROIs) around the cell-containing regions.
//It requires a folder containing all the images to be analyzed. Images have to be 1 channel .tiff format. Minimal modifications are required for multichannel (composite) images
//If images are .tif, replace the extension .tiff by .tif (or other format) where corresponds
//It will create a folder containing the specified ROI for each slice that will be used in Macro_II
//Questions @ https://github.com/JRamirez-F/   or open a topic in https://forum.image.sc/ and mention @J_Ramirez 


dir1=getDirectory("Open Folder");
list=getFileList(dir1);
dir2=dir1+"/selections/";
File.makeDirectory(dir2);
list=Array.sort(list);
time = getTime();
for(i=0; i<list.length; i++)
	{
		if (endsWith(list[i], ".tiff"))//Modify extension if needed
			{
			print(list[i]);
			open(dir1+list[i]);
			filename_clean = File.nameWithoutExtension();
			setTool(2);
			waitForUser("Create selection around cell area if any. \n Multiple region selection allowed by pressing shift");
			sel=selectionType() ;
				if (sel!=-1)
					{
					saveAs("Selection", dir2+"sel_"+filename_clean+".roi");
					}
				else{print("No selection performed in slice "+filename_clean);}
			close("*");
			}
	}
print("Done!");
print("Whole process took you "+(getTime()-time)+" msec");
