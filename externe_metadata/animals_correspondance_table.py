import os
import csv
import re

def create_correspondence_table(root_directory, output_csv_file):
    """
    Generates a CSV lookup table from a directory of subject folders.
    Arguments:
        root_directory (str): Path to the folder containing subject directories.
        output_csv_file (str): Path of the CSV file to generate.
    """
    headers = ["Path", "SubjectName", "Sample", "GUID", "SecurityNumber"]
    print(f"Reading directory: {root_directory}...")
    rows_to_write = []
    
    if os.path.exists(root_directory):
        for folder_name in sorted(os.listdir(root_directory)):
            full_path = os.path.join(root_directory, folder_name)
            if os.path.isdir(full_path):
                temp_name = folder_name.removeprefix("sub-").strip()
                
                # FIX: Extraire juste le nom (Fenouil, Nuphar, etc.)
                # Pattern: 1-Fenouil-MTO10092101 -> Fenouil
                match = re.search(r'\d+-([A-Za-z]+)-', temp_name)
                if match:
                    cleaned_name = match.group(1)
                else:
                    cleaned_name = temp_name if temp_name else ""
                
                row = [
                    full_path,      
                    cleaned_name,   
                    "Cx",           
                    "",             
                    "",             
                ]
                rows_to_write.append(row)
                status = cleaned_name if cleaned_name else "[EMPTY - TO BE FILLED]"
                print(f" -> Subject found: {folder_name} | Name: {status}")
    else:
        print(f"Error: The root directory '{root_directory}' does not exist!")
        return
    
    print(f"Writing csv file {output_csv_file}...")
    try:
        with open(output_csv_file, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows_to_write)
        print("Subject correspandance table created ")
    except IOError as e:
        print(f"Error writing file: {e}")

if __name__ == "__main__":
    my_root_folder = "/envau/work/nit/users/boudlal.h/original-dataset"
    my_output_file = "subjects_correspondence.csv"
    create_correspondence_table(my_root_folder, my_output_file)