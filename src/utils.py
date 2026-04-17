import re, os, sys, json, cssutils
from typing import Literal
from cssutils.css import CSSStyleSheet, CSSStyleRule, CSSStyleDeclaration
from bs4 import BeautifulSoup, NavigableString

from src.constants import (
    ABBREVIATION_CLASS,
    FRM_TYPE,
    OUTPUT_DOC_NAME,
    PERM_CSS_FILE,
    REFERENCE_DOC,
    TO_TYPE,
    CONSOLIDATED_MD_NAME,
    CONSOLIDATED_HTML_NAME,
    ETSI_INITIAL_FILES,
    DEFAULT_CLAUSES,
    DEFAULT_HTML_CLAUSES,
    DEFAULT_ANNEXES,
    ETSI_FINAL_FILES,
    SCOPE,
    REFS,
    DEFS
)

cssutils.log.setLevel("FATAL")  # Suppress irrelevant warnings and errors


# region Warning and Error tags
def p_warning(text: str):
    return f"\033[1m\033[33mWARNING:\033[0m {text}"


def p_error(text: str):
    return f"\033[1m\033[31mERROR:\033[0m {text}"


def p_label(text: str):
    return f"\033[4m\033[1m{text}\033[0m"


# endregion


# region Validators for script arguments
def validate_src_directory(path):
    """
    Ensures the provided source directory is valid.

    #### Args
      `path`: The user-defined source destination provided through the src flag
    """
    if not os.path.isdir(path):
        print(f"{p_error} Source path {p_label(path)} is not a valid directory")
        sys.exit(1)


def validate_type(file_type, is_src: bool):
    """Ensure that the source and destination file types are HTML or Markdown"""
    acceptable_src_types = {"html_dirty", "html", "md"}
    acceptable_dest_types = {"html", "md", "docx"}

    if (is_src and file_type not in acceptable_src_types) or (
        not is_src and file_type not in acceptable_dest_types
    ):
        print(
            f'File type {p_label(file_type)} is not an acceptable file type\nAcceptable types: "html", "md"'
        )
        sys.exit(1)


def validate_conversion(frm: FRM_TYPE, to: TO_TYPE):
    """
    Ensures that the conversion is of one of the following valid types:
    - `HTML` -> `Markdown` OR `Docx`
        - Includes dirty `HTML` -> clean `Markdown`
    - `Markdown` -> `HTML` OR `Docx`

    If not, prints an error and exits
    """
    VALID_CONVERSIONS = [
        ["html", "md"],
        ["html_dirty", "md"],
        ["md", "html"],
        ["md", "docx"],
        ["html", "docx"],
    ]

    if [frm, to] not in VALID_CONVERSIONS:
        print(
            f"{p_error} Invalid destination type {p_label(to)} for source type {p_label(frm)}"
        )
        sys.exit(1)


def validate_file_order_json(json_file: str, is_conv_md_to_html: bool):
    """Various validation checks for the filepath provided by the `--file_order` argument and, if necessary, print any warnings and errors and exit the script as necessary."""

    def is_json_malformed():
        with open(json_file, "r") as file:
            json_data = json.load(file)

        for key in ["clauses", "annexes"]:
            if key not in json_data:
                print(
                    p_error(
                        f"Missing key {p_label(key)} in JSON file at {p_label(json_file)}"
                    )
                )
                return True

            if not isinstance(json_data[key], list):
                print(
                    p_error(
                        f"{p_label(json_file)}: Value at {p_label(key)} must be a list of strings"
                    )
                )
                return True

            if not all(isinstance(item, str) for item in json_data[key]):
                print(
                    p_error(
                        f"{p_label(json_file)}: Value at {p_label(key)} must be a list of strings"
                    )
                )
                return True

            for item in json_data[key]:
                if re.search(r"\.(?:md|html)$", item):
                    print(
                        p_error(
                            f"{p_label(json_file)}: Value {item} in {p_label(key)} must not contain file extensions"
                        )
                    )
                    return True

        return False

    if is_conv_md_to_html:
        if not os.path.exists(json_file):
            print(p_error(f"No file found at {p_label(json_file)}"))
            sys.exit(1)

        if json_file and not json_file.endswith(".json"):
            print(p_error(f"Provided file {p_label(json_file)} is not a JSON file."))
            sys.exit(1)

        if is_json_malformed():
            # Appropriate error message is printed in `is_json_malformed()`
            sys.exit(1)

    else:
        if json_file:
            print(
                p_warning("No file ordering JSON will be used during this conversion.")
            )


def are_files_present(
    src_dir: str,
    clauses: list[str] = DEFAULT_CLAUSES,
    annexes: list[str] = DEFAULT_ANNEXES,
):
    """Assess whether always-present files and clause and annex files are present. If any are missing, print warnings or errors as needed and return `False`. If all necessary files are present, return `True`."""
    # Ensure all standard ETSI files are present
    for filelist in [ETSI_INITIAL_FILES, ETSI_FINAL_FILES]:
        for file in filelist:
            if not os.path.exists(os.path.join(src_dir, f"{file}.md")):
                print(
                    p_error(
                        f"File {p_label(f'{file}.md')} not found in source directory {p_label(src_dir)}"
                    )
                )
                return False

    # Assess and handle clauses and annexes
    for file_list in [clauses, annexes]:
        for file in file_list:
            is_file_existant = os.path.exists(os.path.join(src_dir, f"{file}.md"))

            if file_list != DEFAULT_CLAUSES and file_list != DEFAULT_ANNEXES:
                if not is_file_existant:
                    # Print an error and exit the script
                    print(
                        p_error(
                            f"File {p_label(f'{file}.md')} not found in source directory {p_label(src_dir)}"
                        )
                    )
                    return False

            else:
                if not is_file_existant:
                    # Print warning and continue
                    print(
                        p_warning(
                            f"File {p_label(f'{file}.md')} not found in source directory {p_label(src_dir)}, continuing on"
                        )
                    )
                    continue

    return True


# endregion


# region Command Generators
def get_html_to_md_command(md_input_path: str, output_path: str):
    """
    Returns an array containing elements of the Pandoc command to convert from HTML to Markdown.

    ### Arguments
    - `md_input_path`: The absolute or relative path of the preprocessed HTML file generated during the preprocessing step.
    - `output_path`: The absolute or relative path to which the generated Markdown file will be saved.

    ### Command

    NOTE: The verbose destination Markdown format specified by the `-t` parameter forces Pandoc to generate grid tables.

    `pandoc -f html <md_input_path> -t markdown-pipe_tables-simple_tables-multiline_tables+grid_tables --wrap=none -o <output_path> --lua-filter=html_to_md.lua`
    """
    command = [
        "pandoc",
        "-f",
        "html",
        md_input_path,
        "-t",
        "markdown-pipe_tables-simple_tables-multiline_tables+grid_tables",
        "--wrap=none",
        "-o",
        output_path,
        "--lua-filter=html_to_md.lua",
    ]

    return command


def get_md_to_html_command(
    src: str, dest: str, consolidated_md_path: str, css_src: list[str]
):
    """
    ### Description
    Returns an array containing elements of the Pandoc command to convert from Markdown to HTML.

    ### Arguments
    - `src`: The source directory containing Markdown files to convert to HTML
    - `dest`: The destination directory that will contain the generated HTML files
    - `consolidated_md_path`: The absolute or relative path to a single Markdown file that contains the contents of all the Markdown files to convert to HTML.
    - `css_src`: A list of absolute or relative paths to CSS source files that the generated HTML will use. The class names will correspond to those used in the Pandoc-formatted tags in the Markdown.

    ### Command

    `pandoc -f markdown <consolidated_md_path> -t chunkedhtml --wrap=none -o <dest> --css=<css_src file 1>{repeated for subsequent CSS files} --standalone --toc --toc-depth 6 --template=official.html --split-level=1 --lua-filter=md_to_html.lua --resource-path=<src>`
    """

    with open(consolidated_md_path, "r", encoding="utf-8") as f:
        md_contents = f.read()
        second_line = md_contents.splitlines()[1] if len(md_contents.splitlines()) > 1 else ""
        elements = second_line.strip().split("]")
        if len(elements) > 1 and elements[0].startswith("[ETSI"):
            title_name = elements[0][1:]  # Remove leading '['
            title_name = title_name.replace("ETSI", "ETSI –")
    command = [
        "pandoc",
        "-f",
        "markdown-smart",
        consolidated_md_path,  # Uses temporary MD file
        "-t",
        "chunkedhtml",
        "--wrap=none",
        "-o",
        dest,
        *[f"--css={css_file}" for css_file in css_src],
        "--standalone",
        "--toc",
        "--toc-depth",
        "6",
        "--template=official.html",
        "--split-level=1",
        "--lua-filter=md_to_html.lua",
        "--lua-filter=md_to_html_2.lua",
        "--lua-filter=md_to_html_3.lua",
        "--variable=title-prefix=" + title_name if 'title_name' in locals() else "''",
        f"--resource-path={src}",
    ]

    return command


def get_html_to_docx_command(dest: str, consolidated_html_path, output_doc_path):
    """
    Returns an array containing elements of the Pandoc command to convert from HTML to Docx.

    ### Arguments
    - `dest`: The destination directory for the generated Docx, used for accessing the `media` directory
    - `consolidated_html_path`: The absolute or relative path to the HTML file containing the consolidated contents of all the HTML files to convert to Docx
    - `output_doc_path`: The absolute or relative path at which to save the generated Docx

    ### Command

    `pandoc -f html <consolidated_html_path> --resouce-path=<dest> -t docx -o <output_doc_path> --lua-filter=html_to_docx.lua --reference-doc={REFERENCE_DOC, that is, customized_reference.docx}`
    """
    command = [
        "pandoc",
        "-f",
        "html",
        consolidated_html_path,
        f"--resource-path={dest}",
        "-t",
        "docx",
        "-o",
        output_doc_path,
        "--lua-filter=html_to_docx.lua",
        f"--reference-doc={REFERENCE_DOC}",
        "--preserve-tabs",
    ]

    return command


# endregion


# region Consolidated File Generators
def handle_consolidated_md(
    action: Literal["create", "delete"],
    src: str,
    consolidated_md_path: str,
    ordered_files: list[str] = None,
):
    """
    For use when converting to HTML. Consolidates the input files into a single file or deletes that file.

    #### Args
    - `action`: Either "create" or "delete", defining the function's behavior
    - `src`: The absolute or relative path to the directory containing the Markdown files to consolidate
    - `consolidated_md_path`: The absolute or relative path to
    """
    if action not in ["create", "delete"]:
        raise ValueError(f'Invalid action {action}, expected "create" or "delete"')

    consolidated_md_name = consolidated_md_path.split("/")[-1]

    def create():
        """Handles creation of the consolidated Markdown file"""

        # Ordering the files for the table of contents
        # Include only the numbered files
        excluded_md_files = [consolidated_md_name, "index.md"]

        create_consolidated_file(src, consolidated_md_path, ordered_files)

        # Clean up temporary files
        for file in os.listdir(src):
            if "--preprocessed--" in file and file not in excluded_md_files:
                os.remove(os.path.join(src, file))

    def delete():
        """Handles deletion of the consolidated Markdown file"""
        if os.path.exists(consolidated_md_path):
            os.remove(consolidated_md_path)

    if action == "create":
        create()

    if action == "delete":
        delete()


def get_prefix_of_pandoc_html_generated_file(filename):
    prefix = re.match(r"^(\d+)", filename)
    prefix = int(prefix.group(1)) if prefix else float("inf")
    return prefix


def handle_html_consolidation(
    action: Literal["create", "delete"],
    src: str,
    consolidated_html_path: str,
):
    """
    Consolidates all the input HTML files into a single HTML file for conversion to Docx or deletes the consolidated file, depending on the value passed to `action`.

    #### Args
    `action`: `"create"` or `"delete"`, specifies whether to create or delete the file
    `src`: The source directory containing HTML Files to consolidate
    `consolidated_html_path`: The absolute or relative directory at which to save/from which to delete the consolidated HTML file
    """
    if action not in ["create", "delete"]:
        raise ValueError(f'Invalid action {action}, expected "create" or "delete"')

    def create():
        """Handles creation of the consolidated HTML file"""

        # Ordering the files for the table of contents
        # Include only the numbered files
        excluded_html_files = [CONSOLIDATED_HTML_NAME, "index.html"]

        clauses = DEFAULT_HTML_CLAUSES
        annexes = DEFAULT_ANNEXES
        ordered_files = order_local_files_by_prefix(src, excluded_html_files, "html", clauses, annexes)
        create_consolidated_file(src, consolidated_html_path, ordered_files)

        # Clean up temporary files
        for file in os.listdir(src):
            if "--preprocessed--" in file and file not in excluded_html_files:
                os.remove(os.path.join(src, file))

    def delete():
        """Handles deletion of the consolidated HTML file"""
        if os.path.exists(consolidated_html_path):
            os.remove(consolidated_html_path)

    if action == "create":
        create()

    if action == "delete":
        delete()


# endregion


# region Files helpers
def get_file_order(
    src_dir: str,
    clauses: list[str],
    annexes: list[str],
):
    """Return a list of strings defining the order in which the files should be processed during conversion. If no list of clauses is provided, use the default clauses. If no list of annexes is provided, use the default annexes."""

    def is_file_in_list(filename: str):
        """Return `True` if this file or a file with a name like this one's name is already in the list defining the file order, otherwise `False`"""
        nonlocal new_file_order

        filename = filename.split(".")[0]  # Remove file extension

        for added_file in new_file_order:
            if filename in added_file:
                return True

        return False

    # Begin the list
    new_file_order = ETSI_INITIAL_FILES
    clauses_ordered = []
    annexes_ordered = []

    # Assess and handle clauses and annexes
    for file_list, item_prefix in [(clauses, "clause-"), (annexes, "annex-")]:
        for file in file_list:
            new_file_order.append(file)

        if item_prefix == "clause-":
            clauses_ordered.extend(file_list)
        elif item_prefix == "annex-":
            annexes_ordered.extend(file_list)

        # Add other clauses and files in alphabetical order
        for filename in sorted(os.listdir(src_dir)):
            if filename.startswith(item_prefix) and not is_file_in_list(filename):
                name = os.path.splitext(filename)[0]  # Filename without extension

                if name not in clauses:
                    new_file_order.append(name)

                    if item_prefix == "clause-":
                        clauses_ordered.append(name)
                    elif item_prefix == "annex-":
                        annexes_ordered.append(name)

    # End the list
    new_file_order.extend(ETSI_FINAL_FILES)

    return new_file_order, clauses_ordered, annexes_ordered


def get_output_doc_path(dest: str):
    """
    Returns the path at which the generated Docx is saved/from which the generated Docx is accessed

    ### Arguments
    `dest`: The destination directory at in which the Docx should be saved
    """
    return f"{dest}/{OUTPUT_DOC_NAME}"


def apply_renaming_logic(text: str, filename: str, postfix: str) -> str:
    new_filename = filename
    if postfix == "md":
        if text.startswith("::: ZA"):
            new_filename = f"front-page.{postfix}"
        else:
            header_regex = r"^# (\d+)"
            filename_regex = (
                r"^\d+-([\w-]+?)\.md$" if postfix == "md" else r"^\d+-([\w-]+?)\.html$"
            )
            if text.startswith("# Annex"):
                new_filename = f"annex-{text.split()[2].lower()}.{postfix}"
            elif re.match(header_regex, text):
                match = re.match(header_regex, text)
                chapter_number = match.group(1)
                new_filename = f"clause-{chapter_number}.{postfix}"
            else:  # it is not a chapter with a number or an annex
                match = re.match(filename_regex, filename)
                if match:
                    new_filename = f"{match.group(1)}.{postfix}"
    else:  # postfix == "html"
        soup = BeautifulSoup(text, "html.parser")

        if soup.find("div", class_="ZA"):
            new_filename = f"front-page.{postfix}"
        else:
            title_tag = soup.find("h1", id=True)
            title = title_tag.get_text()
            if title.startswith("Annex"):
                annex_number = title.split()[1].lower().replace(":", "")
                new_filename = f"annex-{annex_number}.{postfix}"
            else:
                header_regex = r"^(\d+)\s"
                match = re.match(header_regex, title)
                if match:
                    chapter_number = match.group(1)
                    if postfix == "md" and chapter_number == "1":
                        new_filename = f"{SCOPE}.{postfix}"
                    elif postfix == "md" and chapter_number == "2":
                        new_filename = f"{REFS}.{postfix}"
                    elif postfix == "md" and chapter_number == "3":
                        new_filename = f"{DEFS}.{postfix}"
                    else:
                        new_filename = f"clause-{chapter_number}.{postfix}"
                else:
                    # it is a clause without a number, just use the filename without the leading number
                    new_filename = re.sub(r"^\d+-", "", filename).lower()
    return new_filename


def get_dirty_filenames_mapping_with_expected_filenames(dir_path: str):
    """
    Returns a mapping of dirty filenames to their expected clean counterparts
    """
    mapping = {}
    filenames = sorted(
        [
            f
            for f in os.listdir(dir_path)
            if f.endswith(".html") and not f == "index.html"
        ],
        key=get_prefix_of_pandoc_html_generated_file,
    )

    for filename in filenames:
        with open(os.path.join(dir_path, filename), "r", encoding="utf-8") as file:
            expected_filename = apply_renaming_logic(file.read(), filename, "html")
        mapping[filename] = expected_filename

    return mapping


def order_local_files_by_prefix(
    src: str,
    excluded_files: list[str],
    type: Literal["html", "md"],
    clauses: list[str] = DEFAULT_CLAUSES,
    annexes: list[str] = DEFAULT_ANNEXES,
):
    if type not in ["html", "md"]:
        raise ValueError(f"Invalid type: {type}")

    original_files = [
        file
        for file in os.listdir(src)
        if "--preprocessed--" in file
        and file.endswith(f".{type}")
        and file not in excluded_files
    ]

    files_order, _, _ = get_file_order(src, clauses, annexes)

    ordered_files = []
    for prefix in files_order:
        matching_files = [
            filename
            for filename in original_files
            if re.match(rf"--preprocessed--{re.escape(prefix)}[.-]", filename)
        ]
        ordered_files.extend(matching_files)
    return ordered_files


def create_consolidated_file(src: str, consolidated_file_path: str, files: list[str]):
    """
    Creates a consolidated file from the provided list of files.

    ### Arguments
    - `src`: The source directory containing the files to consolidate
    - `consolidated_file_path`: The path to the consolidated file to create
    - `files`: A list of file names to consolidate

    ### Returns
    - The path to the consolidated file and its contents
    """

    consolidated_contents = ""

    # Create a temporary file with the consolidated contents
    for file in files:
        html_file_path = os.path.join(src, file)
        with open(html_file_path, "r", encoding="utf-8") as html:
            consolidated_contents += f"{html.read()}\n"

    with open(consolidated_file_path, "w", encoding="utf-8") as c_html:
        c_html.write(consolidated_contents)


# endregion


# region BeautifulSoup Type Checkers
def is_whitespace_navstr(element):
    """
    ### Description
    Returns `True` if `element` is an instance of a `NavigableString` composed of nothing but whitespace, otherwise returns `False`.
    """
    if isinstance(element, NavigableString) and not element.strip():
        return True

    return False


# endregion


# region Other helpers
def get_consolidated_md_path(src: str):
    """
    ### Description
    Returns the path at which to store/from which to retrieve the consolidated Markdown file

    ### Arguments
    `src`: The source directory containing the Markdown files to consolidate
    """
    return os.path.join(src, CONSOLIDATED_MD_NAME)


def get_consolidated_html_path(src: str):
    """
    ### Description
    Returns the path at which to store/from which to retrieve the consolidated HTML file

    ### Arguments
    `src`: The source directory containing the HTML files to consolidate
    """
    return os.path.join(src, CONSOLIDATED_HTML_NAME)


def get_css_classes(
    classes_to_get: Literal["all", "empty", "monospaced", "bullets"],
    css_files: list[str],
):
    """
    Returns a sorted list of CSS classes from the CSS source according to some restriction defined by `classes_to_get`.
    ### Arguments
    - `classes_to_get`: The desired subgroup of classes
    - `css_files`: A list of relative or absolute paths to CSS source files

    #### Values for `classes_to_get`
    - `"all"`
      The sorted list will contain every class name
    - `"empty"`
      The sorted list will contain only classes that contain no properties. Used during cleanup when converting a "dirty" HTML to Markdown.
    - `"monospaced"`
      The sorted list will contain only classes that apply monospaced fonts to the text.
      ##### Monospaced fonts:
        - Courier New
        - Roboto Mono
        - Monospace
    """

    def get_regex():
        """Returns the regex corresponding to the type of classes to get defined by `classes_to_get`"""
        match classes_to_get:
            case "all":
                return r"\.([\w\_\-]+)\b"

            case "empty":
                return r"\.([\w\-_]+?)\s*\{\s*\}"

            case "monospaced":
                monospaced_fonts = {"Courier New", "Roboto Mono", "Monospace"}
                monospaced_fonts = "|".join(
                    [re.escape(font) for font in monospaced_fonts]
                )
                monospaced_class_regex = (
                    rf"\.([\w\-_]+)\s*{{[^}}]*font-family\s*:\s*[^;{{}}]*"
                    rf"(?:{monospaced_fonts})[^;{{}}]*;"
                )
                return monospaced_class_regex

            case "bullets":
                return r"\.(B\d\w*?)\s*\{[^\}]+?\}"

            case _:
                return

    regex = get_regex()
    classes = set()

    for css_file in css_files:
        if os.path.exists(css_file) and css_file != "customCSS.css":
            css_contents = open(css_file, "r", encoding="utf-8").read()
            classes.update(re.findall(regex, css_contents))

    if classes_to_get == "empty" and ABBREVIATION_CLASS in classes:
        classes.remove(ABBREVIATION_CLASS)

    return sorted(classes)


def get_bold_italic_underline_css_classes(css_styles_src: str):
    """Return three separate sets for CSS classes that apply bolding, italicization, and underlining"""
    sheet: CSSStyleSheet = cssutils.parseFile(css_styles_src)
    bold = set()
    italic = set()
    underline = set()

    for rule in sheet:
        if rule.type != rule.STYLE_RULE:
            continue

        rule: CSSStyleRule

        for selector in rule.selectorList:
            classname = selector.selectorText.lstrip(".")

            style: CSSStyleDeclaration = rule.style

            if style.getPropertyValue("font-weight").lower() == "bold" or (style.getPropertyValue("font-weight").isdigit() and int(style.getPropertyValue("font-weight")) >= 600):
                bold.add(classname)

            if style.getPropertyValue("font-style").lower() == "italic":
                italic.add(classname)

            if style.getPropertyValue("text-decoration").lower() == "underline":
                underline.add(classname)

    return bold, italic, underline


def try_reformat_json(text: str) -> str:
    """
    Try to parse and reformat *text* as JSON with 2-space indentation.
    Handles both complete JSON values (objects/arrays) and JSON fragments
    (key-value pairs such as ``"key": value``).
    Preserves comments (// and /* */) and non-conforming text like "...etc", "… etc".
    Returns the reformatted text on success, or the original text unchanged
    on failure (e.g. for BNF/ABNF grammars).
    """
    stripped = text.strip()

    # Helper function to find positions of quoted strings
    def find_string_ranges(text):
        """Return list of (start, end) tuples for all quoted strings in text."""
        ranges = []
        in_string = False
        start = 0
        i = 0
        while i < len(text):
            if text[i] == '"' and (i == 0 or text[i - 1] != "\\"):
                if not in_string:
                    start = i
                    in_string = True
                else:
                    ranges.append((start, i + 1))
                    in_string = False
            i += 1
        return ranges

    # Helper to check if position is inside a quoted string
    def is_in_string(pos, string_ranges):
        """Check if position is within any of the string ranges."""
        for start, end in string_ranges:
            if start <= pos < end:
                return True
        return False

    # Store preserved items with placeholders
    preserved = []  # List of (placeholder, original_content)
    placeholder_idx = 0

    def make_placeholder():
        nonlocal placeholder_idx
        ph = f"__PRESERVED_{placeholder_idx}__"
        placeholder_idx += 1
        return ph

    cleaned = stripped
    string_ranges = find_string_ranges(cleaned)

    # Replace single-line comments with placeholders (// style, but NOT in URLs)
    # Match // only when NOT inside strings and not preceded by :
    def replace_comment(match):
        nonlocal preserved, string_ranges
        if is_in_string(match.start(), string_ranges):
            return match.group(0)
        content = match.group(0)
        placeholder = make_placeholder()
        preserved.append((placeholder, content))
        return placeholder

    # Match // at start of line or after whitespace/brackets, but not after :
    cleaned = re.sub(
        r"(?<!:)(?<=[\[\{\,\s])//[^\n]*|^//[^\n]*",
        replace_comment,
        cleaned,
        flags=re.MULTILINE,
    )

    # Update string ranges after first substitution
    string_ranges = find_string_ranges(cleaned)

    # Replace non-conforming patterns with placeholders
    def replace_nonconform(match):
        nonlocal preserved, string_ranges
        if is_in_string(match.start(), string_ranges):
            return match.group(0)
        content = match.group(0)
        placeholder = make_placeholder()
        preserved.append((placeholder, content))
        return f'"{placeholder}"'  # Wrap in quotes so JSON parser accepts it

    # Match various forms: "… etc", "...etc", "etc.", "..." but NOT inside quoted strings
    # Look for these patterns outside of strings only
    non_conform_pattern = r"(?:^|\s)((?:\.{3,}|…)(?:\s*etc\.?)?|etc\.)(?=\s|,|$)"
    cleaned = re.sub(
        non_conform_pattern,
        lambda m: (
            m.group(0)[: m.start(1) - m.start(0)] + replace_nonconform(m)
            if not is_in_string(m.start(1), string_ranges)
            else m.group(0)
        ),
        cleaned,
        flags=re.MULTILINE,
    )

    # Try to format the cleaned JSON
    formatted = None
    is_fragment = False

    # Try as a self-contained JSON value
    try:
        parsed = json.loads(cleaned)
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        # Try as a JSON fragment
        try:
            parsed = json.loads("{" + cleaned + "}")
            formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
            # Strip the outer braces and remove one level of indentation
            lines_fmt = formatted.split("\n")
            inner = [
                line[2:] if line.startswith("  ") else line for line in lines_fmt[1:-1]
            ]
            formatted = "\n".join(inner)
            is_fragment = True
        except (json.JSONDecodeError, ValueError) as e:
            # print(f"Warning: Failed to parse as JSON:\n{cleaned}\nReturning original text.")
            # print("Error details:", flush=True)
            # print(f"Error: {e}")
            pass

    # If formatting failed, return original
    if formatted is None:
        return text

    # If no preserved items, return formatted
    if not preserved:
        return formatted

    # Restore preserved items
    for placeholder, original in preserved:
        # Remove quotes around placeholder if present (we added them for JSON parsing)
        formatted = formatted.replace(f'"{placeholder}"', original)
        # Also try without quotes in case it appears in comments
        formatted = formatted.replace(placeholder, original)

    return formatted


def combine_biu_classes():
    """Combines bold and italic classes in the separate lists from `get_bold_italic_underline_css_classes` into a single list"""
    CSS_BOLD, CSS_ITALIC, CSS_UNDERLINE = get_bold_italic_underline_css_classes(PERM_CSS_FILE)
    CUSTOM_CLASSES = ["HTML-Code", "HTML-Variable", "HTML-Keyboard", "HTML-Error", "HTML-Sample", "HTML-Definition"] 

    return set(cls for group in [CSS_BOLD, CSS_ITALIC, CSS_UNDERLINE, CUSTOM_CLASSES] for cls in group)

def int_to_letter(number: int):
    """Converts a 1-based integer to a corresponding uppercase letter (A=1, B=2, etc.)"""
    if 1 <= number <= 26:
        return chr(number + 64)  # 65 is the ASCII code for 'A'
    raise ValueError("Number must be between 1 and 26.")

# endregion
