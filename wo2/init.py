import argparse, os, sys, shutil

parser = argparse.ArgumentParser()
parser.add_argument("--folder", help="Folder which will contains your content")
parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files")
args = parser.parse_args()

if not args.folder:
    parser.error("Folder argument is required")
    sys.exit(1)

current_folder = os.getcwd()
generated_files_folder = os.path.join(current_folder, "GENERATED_FILES")

if not os.path.exists(generated_files_folder):
    os.makedirs(generated_files_folder)

folder = os.path.join(generated_files_folder, args.folder)
overwrite = args.overwrite
if os.path.exists(folder) and not overwrite:
    parser.error(f"Folder {folder} already exists, use --overwrite to overwrite it")
    sys.exit(1)

try:
    if os.path.exists(folder) and overwrite:
        shutil.rmtree(folder)

    os.makedirs(folder)

    # copy ETSIstyles.css and customCSS.css files into folder
    shutil.copy2("ETSIstyles.css", folder)
    shutil.copy2("customCSS.css", folder)

    # create md folder inside
    md_folder = os.path.join(folder, "md")
    os.makedirs(md_folder)

    # create media folder inside md
    media_folder = os.path.join(md_folder, "media")
    os.makedirs(media_folder)

    print("Folder structure created successfully.")
except Exception as e:
    print(f"Error creating folder structure: {e}")
    # delete any created folders
    shutil.rmtree(folder, ignore_errors=True)
    sys.exit(1)
