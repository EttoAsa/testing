# region Imports
import argparse, subprocess, os, sys, shutil, json
from bs4 import BeautifulSoup
from html_diff import make_trackchanges_diff
from src.constants import (
    FILEGEN_DIR,
    TO_DOCX_EXCLUDED_HTML_FILES,
    TO_MD_EXCLUDED_HTML_FILES,
    SCOPE,
    REFS,
    DEFS,
    GIT_STASH_STATUSES,
)
from src.utils import (
    get_consolidated_html_path,
    get_dirty_filenames_mapping_with_expected_filenames,
    get_html_to_docx_command,
    get_output_doc_path,
    p_error,
    p_label,
    validate_src_directory,
    validate_type,
    validate_conversion,
    validate_file_order_json,
    are_files_present,
    handle_consolidated_md,
    get_html_to_md_command,
    get_md_to_html_command,
    get_consolidated_md_path,
)
from src.time_book import get_timer, set_threshold
import git_helper

from src.to_md.preprocessing import preprocess as preprocess_md
from src.to_md.postprocessing import postprocess as postprocess_md

from src.to_html.preprocessing import preprocess as preprocess_html
from src.to_html.postprocessing import postprocess as postprocess_html
from src.to_html.postprocessing import clone_toc_in_file as clone_toc_in_file_html

from src.to_docx.preprocessing import preprocess as preprocess_docx
from src.to_docx.postprocessing import postprocess as postprocess_docx

# endregion

# region Setup
# Define the arguments the user can provide to the script
parser = argparse.ArgumentParser(
    description=f'Converts from {p_label("HTML")} to {p_label("Markdown")} or {p_label("Docx")} and from {p_label("Markdown")} to {p_label("HTML")}'
)

# Required arguments
parser.add_argument(
    "--frm",
    required=True,
    choices=["html_dirty", "html", "md"],
    help='Source Types: "html_dirty" for HTML to run additional processing on to produce desired formatting, "html" for HTML that is already properly formatted, or "md" for Markdown',
)
parser.add_argument(
    "--to",
    required=True,
    choices=["html", "md", "docx"],
    help='Destination Types: "html", "md", or "docx"',
)
parser.add_argument(
    "--folder",
    required=True,
    help=f'The name of the folder within {p_label("GENERATED_FILES")} to place the converted files. BEST PRACTICE: Use a short term by which the document can be uniquely identified, for example, {p_label("API")} or {p_label("primer")}.',
)
parser.add_argument(
    "--src",
    help=f"Optionally, provide the path of the source directory rather than generate it. The source will be inferred from the contents of the folder passed with the {p_label('--folder')} argument if this argument is not provided.",
)
parser.add_argument(
    "--file_order",
    help=f"Optionally, when converting from {p_label('Markdown')} to {p_label('HTML')}, provide the relative or absolute path to a JSON file containing the order in which the files should be arranged in the final produced HTML. If a file is not provided, the default ordering will be used.  The default ordering parses first clauses (named {p_label(f'clause-{{number 4 - 20}}')}), then annexes (named {p_label(f'annex-{{letter a - z}}')}).  Any files in the source directory not included in the list will be included at the end in alphabetical order. However, any files present in the JSON that are not present in the source directory will cause an error and the script to exit prematurely.",
)
parser.add_argument(
    "--diff",
    action="store_true",
    help="Optionally, when converting from Markdown to HTML, highlight differences between the current Markdown files and the previous version stored on disk. When using --diff-git, the target branch or commit is used as the comparison source.",
)
parser.add_argument(
    "--diff-git",
    nargs="?",
    const=True,
    help="Optionally, when provided, uses Git to get the target branch or commit and use it as the source of the diff when converting from Markdown to HTML. This argument overrides the diff command.",
)
parser.add_argument(
    "--time",
    action="store_true",
    help="Optionally, print a timing report at the end of the conversion process, showing the time taken for each section of the process. This can be used to identify any bottlenecks in the conversion process and optimize them for better performance.",
)
parser.add_argument(
    "--no-lazy-toc",
    action="store_true",
    help="Optionally, disable the lazy loading of the Table of Contents (ToC) in the generated HTML files when converting from Markdown to HTML. By default, the ToC is loaded lazily to improve performance, but this option forces the ToC to be cloned in all the HTML files.",
)
parser.add_argument(
    "--extra-outputs",
    choices=["pdf", "epub", "pdf,epub"],
    help='Optionally, when converting from "html" to "docx", select extra output formats: "pdf", "epub", or "pdf,epub".',
)

args = parser.parse_args()

if args.src:
    validate_src_directory(args.src)


# Ensure the conversion is valid
validate_conversion(args.frm, args.to)

if args.extra_outputs and not (args.frm == "html" and args.to == "docx"):
    print(
        p_error(
            f"The {p_label('--extra-outputs')} argument is only valid when converting from {p_label('html')} to {p_label('docx')}."
        )
    )
    sys.exit(1)

# Validate source and destination type and create destination directory if necessary
validate_type(args.frm, is_src=True)
validate_type(args.to, is_src=False)

# Global variables and helpers
# Argument values
FOLDER: str = args.folder

IS_DIFF: bool = bool(args.diff)

IS_GIT_DIFF: bool = args.diff_git is not None

GIT_CHECKOUT_NAME: str = (
    args.diff_git if IS_GIT_DIFF and isinstance(args.diff_git, str) else ""
)

TIMER_ENABLED: bool = bool(args.time)

NO_LAZY_TOC: bool = bool(args.no_lazy_toc)

if IS_GIT_DIFF and IS_DIFF:
    print("Warning: --diff-git cannot be used together with --diff.")
    print("--diff-git overrides --diff. Continuing with --diff-git behavior.")
if IS_GIT_DIFF and not IS_DIFF:
    IS_DIFF = True

if not args.src and IS_DIFF and IS_GIT_DIFF:
    print(
        p_error(
            f"When using the {p_label('--diff-git')} argument, the {p_label('--src')} argument must be provided with a valid path to a Git repository."
        )
    )
    sys.exit(1)

SRC_TYPE: str = "html" if str(args.frm).startswith("html") else args.frm
if args.src and not (args.frm == "html" and args.to == "docx"):
    SRC = args.src
else:
    if args.src and args.frm == "html" and args.to == "docx":
        print(
            f"Warning: The {p_label('--src')} argument is ignored when converting from {p_label('html')} to {p_label('docx')}."
        )
    SRC = f"{FILEGEN_DIR}/{FOLDER}/{args.frm}"  # Use args.frm to get "html_dirty"

IS_CLEANUP: bool = str(args.frm) == "html_dirty"

DEST_TYPE: str = args.to
DEST: str = f"{FILEGEN_DIR}/{FOLDER}/{DEST_TYPE}"

# Assess file order
FILE_ORDER_JSON: str = args.file_order or None

if FILE_ORDER_JSON:
    validate_file_order_json(FILE_ORDER_JSON, SRC_TYPE == "md" and DEST_TYPE == "html")

if SRC_TYPE == "md" and DEST_TYPE == "html":
    if FILE_ORDER_JSON:
        # Use clauses and annexes from the JSON file
        with open(FILE_ORDER_JSON, "r") as file:
            json_data = json.load(file)
            clauses = json_data.get("clauses")
            annexes = json_data.get("annexes")

        if not are_files_present(SRC, clauses, annexes):
            # Print error in are_files_present()
            sys.exit(1)

    else:
        # Use default clauses and annexes
        if not are_files_present(SRC):
            # Print error in are_files_present()
            sys.exit(1)

# Get consolidated Markdown path
CONSOLIDATED_MD_PATH = get_consolidated_md_path(SRC)

# Get consolidated HTML path
CONSOLIDATED_HTML_PATH = get_consolidated_html_path(SRC)

# Get output Doc path
OUTPUT_DOC_PATH = get_output_doc_path(DEST)

if IS_CLEANUP:
    FILENAMES_MAPPING = get_dirty_filenames_mapping_with_expected_filenames(SRC)
else:
    FILENAMES_MAPPING = None


# CSS Files
def list_css_files():
    """Returns a list of CSS files. If the source format is dirty HTML, add the CSS file generated by `preprocessing.py` in `saved_files`/`{SRC_TYPE}.css`. Otherwise, include just `ETSIstyles.css` and `customCSS.css`."""
    css_files = ["ETSIstyles.css", "customCSS.css"]

    if IS_CLEANUP:
        generated_css_filepath = f"{FILEGEN_DIR}/{FOLDER}/{FOLDER}.css"

        if not os.path.exists(generated_css_filepath):
            print(
                p_error(
                    f"No generated file {p_label(generated_css_filepath)} in {p_label(f'{FILEGEN_DIR}/{FOLDER}')}"
                )
            )
            sys.exit(1)

        css_files.append(generated_css_filepath)

    return css_files


CSS_SRC = list_css_files()

# Create destination directory
if not os.path.exists(DEST):
    os.makedirs(DEST)

SRC_MEDIA_PATH = os.path.join(SRC, "media")
DEST_MEDIA_PATH = os.path.join(DEST, "media")

# Copy images over
if not os.path.exists(SRC_MEDIA_PATH):
    print(
        p_error(
            f"Source directory {SRC} must contain a media directory containing the images used in the document"
        )
    )
    sys.exit(1)

if os.path.exists(DEST_MEDIA_PATH):
    shutil.rmtree(DEST_MEDIA_PATH)

shutil.copytree(SRC_MEDIA_PATH, DEST_MEDIA_PATH)
# endregion


# region Conversion Logic
def convert(conversion_args=None):
    """
    Converts between Markdown and HTML, based on provided script arguments

    Steps
    1. Preprocess inputs
    2. Convert using Pandoc
    """
    if conversion_args is None:
        conversion_args = args
    with get_timer().section("Convert md to html"):

        def convert_md_to_html():
            """
            Handles conversion from Markdown to HTML.
            #### Steps
            1. Deletes the destination directory, if it is present. When creating chunked HTML, Pandoc requires that the destination directory does not eixst.\n
                **Recommended**: If the destination directory already exists, remove any valuable files beforehand.
            2. Preprocesses Markdown files and consolidates them into a single temporary file
            3. Converts using Pandoc
            4. Deletes the temporary consolidated file created during step 1
            """
            # Setup and preprocessing
            if os.path.exists(DEST):
                shutil.rmtree(DEST)

            filename_numbers_mapping = preprocess_html(
                SRC, SRC_TYPE, CONSOLIDATED_MD_PATH, FILE_ORDER_JSON
            )
            filename_numbers_mapping_path = os.path.join(
                SRC, "filename_numbers_mapping.json"
            )
            with open(filename_numbers_mapping_path, "w") as f:
                json.dump(filename_numbers_mapping, f, indent=4)

            # Conversion
            command = get_md_to_html_command(SRC, DEST, CONSOLIDATED_MD_PATH, CSS_SRC)
            with get_timer().section("Preprocessing: Pandoc md to html conversion"):
                try:
                    subprocess.run(command, check=True, capture_output=True, text=True)
                    os.remove(filename_numbers_mapping_path)
                except subprocess.CalledProcessError as e:
                    print(
                        f"Error converting Markdown files in {SRC} to HTML:\n{e.stderr}"
                    )
                    os.remove(filename_numbers_mapping_path)
                    sys.exit(1)

            # Copy the media directory back over to preserve the emfs, since Pandoc doesn't bring those over
            if os.path.exists(f"{DEST}/media"):
                shutil.rmtree(f"{DEST}/media")

            shutil.copytree(f"{SRC}/media", f"{DEST}/media")

            # Copy ETSIstyles.css into the parent folder
            for css_file in CSS_SRC:
                shutil.copy(css_file, os.path.join(FILEGEN_DIR, FOLDER))
            shutil.copy("advancedTOCLogic.js", DEST)

            # Cleanup the consolidated Markdown
            handle_consolidated_md("delete", SRC, CONSOLIDATED_MD_PATH)

    with get_timer().section("Convert html to md"):

        def convert_html_to_md():
            """
            Handles conversion from HTML to Markdown.

            #### Steps:
            Iterating through input HTML files...
            1. Creates a temporary copy of input HTML file to remove everything but the file's contents
            2. Converts using Pandoc
            3. Deletes the temporary copy of the HTML file created during step 1
            """

            global_headings_id_mapping = {}
            final_html_files = []
            for filename in os.listdir(SRC):
                if (
                    filename.endswith(SRC_TYPE)
                    and filename not in TO_MD_EXCLUDED_HTML_FILES
                ):
                    # Setup and preprocessing
                    input_path = os.path.join(SRC, filename)

                    if (
                        IS_CLEANUP
                    ):  # when coming from a WORD doc, we want to impose the naming logic over pandoc's logic
                        filename = FILENAMES_MAPPING.get(filename, filename)
                    md_input_path = os.path.join(DEST, filename)

                    headings_id_mapping = preprocess_md(
                        input_path,
                        md_input_path,
                        IS_CLEANUP,
                        CSS_SRC,
                        FILENAMES_MAPPING,
                    )

                    if IS_CLEANUP:
                        global_headings_id_mapping.update(headings_id_mapping)

                    filename_without_type = os.path.splitext(filename)[0]
                    if filename_without_type in SCOPE:
                        filename_without_type = f"{SCOPE}"
                    elif filename_without_type in REFS:
                        filename_without_type = f"{REFS}"
                    elif filename_without_type in DEFS:
                        filename_without_type = f"{DEFS}"

                    output_filename = f"{filename_without_type}.{DEST_TYPE}"
                    output_path = os.path.join(DEST, output_filename)
                    final_html_files.append((md_input_path, output_path))

            # Conversion
            for md_input_path, output_path in final_html_files:
                command = get_html_to_md_command(md_input_path, output_path)

                try:
                    subprocess.run(command, check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    print(f"Error converting {filename}:\n{e.stderr}")
                    sys.exit(1)

                # Cleanup the temporary generated HTML
                if os.path.exists(md_input_path):
                    os.remove(md_input_path)

    with get_timer().section("Convert html to docx"):

        def convert_html_to_docx():
            """
            Handles conversion from HTML to a single Docx file.
            """
            html_folder = os.path.join(DEST, "html")
            preprocess_docx(
                SRC, SRC_TYPE, TO_DOCX_EXCLUDED_HTML_FILES, CONSOLIDATED_HTML_PATH
            )

            # Conversion
            command = get_html_to_docx_command(
                DEST, CONSOLIDATED_HTML_PATH, OUTPUT_DOC_PATH
            )

            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                print(
                    p_error(
                        f"Unable to convert HTML files in {SRC} to Docx:\n{e.stderr}"
                    )
                )
                sys.exit(1)

            # Cleanup
            if os.path.exists(CONSOLIDATED_HTML_PATH):
                os.remove(CONSOLIDATED_HTML_PATH)  # Remove temporary generated HTML

    # Convert
    if SRC_TYPE == "html" and DEST_TYPE == "md":
        convert_html_to_md()

    if SRC_TYPE == "html" and DEST_TYPE == "docx":
        convert_html_to_docx()

    if SRC_TYPE == "md" and DEST_TYPE == "html":
        convert_md_to_html()


def get_comparing_folder_from_git():
    # Check if the DIFF_PATH is a git repo
    if not git_helper.is_git_repo(SRC):
        print(
            p_error(f"The provided path at {p_label('--src')} is not a Git repository.")
        )
        sys.exit(1)
    current_branch = git_helper.get_current_branch(SRC)
    if current_branch is None:
        print(
            p_error(
                f"Could not determine the current branch for the Git repository at {p_label('--src')}."
            )
        )
        sys.exit(1)
    # Get the main branch name
    target_to_checkout = (
        GIT_CHECKOUT_NAME
        if GIT_CHECKOUT_NAME
        else git_helper.get_master_branch_name(SRC)
    )
    if not target_to_checkout:
        print(
            p_error(
                f"Could not determine the main branch name for the Git repository at {p_label('--src')}."
            )
        )
        sys.exit(1)
    target_is_branch = git_helper.is_target_a_branch(SRC, target_to_checkout)
    target_is_commit = git_helper.is_target_a_commit(SRC, target_to_checkout)
    current_commit_hash = git_helper.get_current_commit_hash(SRC)
    last_remote_commit_hash = git_helper.get_last_commit_remote_hash(
        SRC, remote_name="origin", branch_name=target_to_checkout
    )
    if target_is_commit and current_commit_hash == target_to_checkout:
        print(
            p_error(
                f"The provided Git commit hash {p_label(target_to_checkout)} is the same as the current commit in the Git repository at {p_label('--src')}. Please provide a different commit hash to compare against."
            )
        )
        sys.exit(1)
    if (
        target_is_branch
        and current_branch == target_to_checkout
        and current_commit_hash == last_remote_commit_hash
    ):
        print(
            p_error(
                f"The provided Git branch name {p_label(target_to_checkout)} is the same as the current branch in the Git repository at {p_label('--src')}. Please provide a different branch name to compare against."
            )
        )
        sys.exit(1)
    # If target_to_checkout is a branch name, get the latest remote commit hash
    if target_is_branch:
        branch_target = target_to_checkout
        target_to_checkout = last_remote_commit_hash
        if not target_to_checkout:
            print(
                p_error(
                    f"Could not retrieve the latest remote commit hash for branch {p_label(branch_target)} in the Git repository at {p_label('--src')}."
                )
            )
            sys.exit(1)
    else:
        branch_target = None
    if (
        load_target_commit(os.path.join(FILEGEN_DIR, f"{FOLDER}-base"))
        == target_to_checkout
    ):
        print(
            f"The base HTML files for commit {p_label(target_to_checkout)} {f'(branch: {p_label(branch_target)}) ' if branch_target else ''}have already been generated. Using existing files for diff..."
        )
        return os.path.join(FILEGEN_DIR, f"{FOLDER}-base", "html")
    # Stash any changes
    changes_stashed = git_helper.stash_changes(SRC)
    if changes_stashed == GIT_STASH_STATUSES.FAILED:
        print(
            p_error(
                f"Could not stash changes in the Git repository at {p_label('--src')}."
            )
        )
        sys.exit(1)
    # Checkout to the target branch/commit
    if not git_helper.checkout(SRC, target_to_checkout):
        print(
            p_error(
                f"Could not checkout to commit {p_label(target_to_checkout)} {f'(branch: {p_label(branch_target)}) ' if branch_target else ''}in the Git repository at {p_label('--src')}."
            )
        )
        restore_original_state(current_branch, changes_stashed)
        sys.exit(1)
    # pull the latest changes
    if target_is_branch and current_branch != branch_target and branch_target:
        print(
            f"Pulling latest changes for branch {p_label(branch_target)} in the Git repository at {p_label('--src')}..."
        )
        if not git_helper.pull_changes(
            SRC, remote_name="origin", branch_name=branch_target
        ):
            print(
                p_error(
                    f"Could not pull latest changes in the Git repository at {p_label('--src')}."
                )
            )
            restore_original_state(current_branch, changes_stashed)
            sys.exit(1)
    # Start a new subprocess to generate the comparing HTML files in a temporary directory
    temp_base_html_dir = os.path.join(FILEGEN_DIR, f"{FOLDER}-base")
    if os.path.exists(temp_base_html_dir):
        shutil.rmtree(temp_base_html_dir)
    os.makedirs(temp_base_html_dir)
    temp_args = argparse.Namespace(
        frm="md",
        to="html",
        folder=f"{FOLDER}-base",
        src=SRC,
        file_order=None,
        diff=None,
        git=None,
    )
    # Run the conversion in the temporary directory
    print(
        f"Generating base HTML files from commit {p_label(target_to_checkout)} {f'(branch: {p_label(branch_target)}) ' if branch_target else ''}for diff..."
    )
    try:
        subprocess.run(
            [
                sys.executable,
                "convert.py",
                "--frm",
                temp_args.frm,
                "--to",
                temp_args.to,
                "--folder",
                temp_args.folder,
                "--src",
                temp_args.src,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(p_error(f"Error generating comparing HTML files:\n{e.stderr}"))
        sys.exit(1)
    finally:
        restore_original_state(current_branch, changes_stashed)
        print(
            f"Restored original Git state. Returning to branch {p_label(current_branch)}..."
        )
    print(f"Base HTML files generated successfully.")
    save_target_commit(target_to_checkout, temp_base_html_dir)
    return os.path.join(FILEGEN_DIR, f"{FOLDER}-base", "html")


def apply_stash(changes_stashed):
    # Apply stashed changes
    if (
        changes_stashed == GIT_STASH_STATUSES.STASHED
        and not git_helper.stash_pop_changes(SRC)
    ):
        print(
            p_error(
                f"Could not apply stashed changes in the Git repository at {p_label('--src')}."
            )
        )
        sys.exit(1)


def return_to_original_branch(original_branch):
    if not git_helper.checkout(SRC, original_branch):
        print(
            p_error(
                f"Could not checkout back to branch {p_label(original_branch)} in the Git repository at {p_label('--src')}."
            )
        )
        sys.exit(1)


def restore_original_state(original_branch, changes_stashed):
    return_to_original_branch(original_branch)
    if changes_stashed == GIT_STASH_STATUSES.STASHED:
        apply_stash(changes_stashed)


def save_target_commit(target_commit, path):
    with open(os.path.join(path, ".gittargetcommit"), "w") as f:
        f.write(target_commit)


def load_target_commit(path):
    target_commit_path = os.path.join(path, ".gittargetcommit")
    if os.path.exists(target_commit_path):
        with open(target_commit_path, "r") as f:
            return f.read().strip()
    return None


### Run script
print("Starting conversion...")
t = get_timer()
with t.section("Launch conversion"):
    convert()
print("Conversion from {} to {} completed successfully.".format(args.frm, args.to))

print("Post-processing started...")

if SRC_TYPE == "html" and DEST_TYPE == "md":
    with t.section("Post-process Markdown files"):
        postprocess_md(DEST, IS_CLEANUP)

if SRC_TYPE == "html" and DEST_TYPE == "docx":
    with t.section("Post-process Docx file"):
        postprocess_docx(OUTPUT_DOC_PATH, args.extra_outputs)

if SRC_TYPE == "md" and DEST_TYPE == "html":
    toc_filename = "index.html"
    toc_path = os.path.join(DEST, toc_filename)
    with t.section("Post-process HTML files"):
        postprocess_html(DEST, NO_LAZY_TOC)
    with t.section("Apply diff to HTML files"):
        if IS_DIFF:
            # default diff_source_dir is GENERATED_FILE/{FOLDER}-base/html
            if IS_GIT_DIFF:
                if not args.src:
                    print(
                        p_error(
                            f"When using the {p_label('--git')} argument, the {p_label('--src')} argument must be provided with a valid path to a Git repository."
                        )
                    )
                    sys.exit(1)
                diff_source_dir = get_comparing_folder_from_git()
            else:
                diff_source_dir = os.path.join(FILEGEN_DIR, f"{FOLDER}-base", "html")
            print(f"Applying diff from source directory: {diff_source_dir}...")
            # Iterate through new HTML files and create diffs
            filename_count_mapping = {}
            for filename in os.listdir(DEST):
                if filename.endswith(".html"):
                    new_file_path = os.path.join(DEST, filename)
                    comparing_file_path = os.path.join(diff_source_dir, filename)
                    # Create diff and overwrite the new file
                    count = make_trackchanges_diff(
                        comparing_file_path, new_file_path, new_file_path
                    )
                    if count and count > 0:
                        filename_count_mapping[filename] = count
            shutil.copy("diffVisualizer.js", DEST)
            toc_soup = None
            if os.path.exists(toc_path):
                with open(toc_path, "r", encoding="utf-8") as f:
                    toc_soup = BeautifulSoup(f, "html.parser")

            def add_diff_count_to_toc_entry(filename, count):
                if toc_soup:
                    for link in toc_soup.find_all("a", href=True):
                        href = link.get("href", "")
                        if (
                            href == filename or href.startswith(f"{filename}#")
                        ):
                            if href.startswith(f"{filename}#"):
                                splitted_href = href.split("#", 1)
                                if "." in splitted_href[1]:
                                    continue
                            link["class"] = link.get("class", []) + [
                                "diff-changes-enable"
                            ]
                            link["data-diff-count"] = count
                            break

            for filename, count in filename_count_mapping.items():
                add_diff_count_to_toc_entry(filename, count)
            if toc_soup is not None:
                with open(toc_path, "w", encoding="utf-8") as f:
                    f.write(str(toc_soup))
            else:
                print(
                    p_error(
                        f"TOC file '{toc_path}' was not found or could not be parsed; diff counts were not applied to the TOC."
                    )
                )
            print(f"Diff completed.")
    with t.section("Clone TOC in HTML files"):
        if NO_LAZY_TOC:
            toc_soup = None
            if os.path.exists(toc_path):
                with open(toc_path, "r", encoding="utf-8") as f:
                    toc_soup = BeautifulSoup(f, "html.parser")
            for filename in os.listdir(DEST):
                if filename.endswith(".html") and filename != toc_filename:
                    file_path = os.path.join(DEST, filename)
                    with open(file_path, "r", encoding="utf-8") as f:
                        soup = BeautifulSoup(f, "html.parser")
                    if toc_soup:
                        soup = clone_toc_in_file_html(soup, toc_soup)
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(str(soup))

if SRC_TYPE == "md" and DEST_TYPE == "docx":
    print("Converting Markdown files to DOCX...")
    work_dir = os.path.join(FILEGEN_DIR, f"{FOLDER}")
    if os.path.exists(work_dir):
        try:
            shutil.rmtree(work_dir)
        except OSError as e:
            print(f"Warning: Could not fully remove {work_dir}: {e}")
            # Try to remove recursively with ignore_errors as fallback
            shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(work_dir)
    md_to_html_args = argparse.Namespace(
        frm="md",
        to="html",
        folder=f"{FOLDER}",
        src=SRC,
        file_order=FILE_ORDER_JSON,
        diff=args.diff,
        diff_git=args.diff_git,
    )
    try:
        print("Generating HTML files from Markdown...")
        with t.section("Generate HTML files from Markdown for DOCX conversion"):
            subprocess.run(
                [
                    sys.executable,
                    "convert.py",
                    "--frm",
                    md_to_html_args.frm,
                    "--to",
                    md_to_html_args.to,
                    "--folder",
                    md_to_html_args.folder,
                    "--src",
                    md_to_html_args.src,
                    *(
                        ["--file_order", md_to_html_args.file_order]
                        if md_to_html_args.file_order
                        else []
                    ),
                    *(
                        (
                            ["--diff-git"]
                            if md_to_html_args.diff_git is True
                            else ["--diff-git", md_to_html_args.diff_git]
                        )
                        if md_to_html_args.diff_git is not None
                        else (["--diff"] if md_to_html_args.diff else [])
                    ),
                ],
                # Note:
                # the case diff_git is not None and diff is False should not happen since --diff-git implies --diff.
                # If changes are done to the logic of how these flags are set, the command construction logic should be updated accordingly.
                check=True,
                capture_output=True,
                text=True,
            )
        html_work_dir = os.path.join(work_dir, "html")
        html_to_docx_args = argparse.Namespace(
            frm="html",
            to="docx",
            folder=f"{FOLDER}",
            src=html_work_dir,
            diff=IS_DIFF,
        )
        print("Converting HTML files to DOCX...")
        with t.section("Convert generated HTML files to DOCX"):
            subprocess.run(
                [
                    sys.executable,
                    "convert.py",
                    "--frm",
                    html_to_docx_args.frm,
                    "--to",
                    html_to_docx_args.to,
                    "--folder",
                    html_to_docx_args.folder,
                    "--src",
                    html_to_docx_args.src,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
    except subprocess.CalledProcessError as e:
        print(p_error(f"Error during conversion:\n{e.stderr}"))
        sys.exit(1)

print("Post-processing completed successfully.")
if TIMER_ENABLED:
    print("Timing report:")
    set_threshold(0.001)
    print(t.report())
# endregion
