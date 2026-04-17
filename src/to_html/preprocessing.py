import os, re, json
import sys
from typing_extensions import Literal
from ..time_book import get_timer

from src.constants import (
    NORMATIVE_REF_FILE,
    INFORMATIVE_REF_FILE,
    DEFAULT_CLAUSES,
    DEFAULT_ANNEXES,
    REFS,
    DIV_START_REGEX,
    DIV_END_REGEX,
    BAD_DIV_DELINEATOR_REGEX,
    REFERENCE_MAPPING_MD_TO_HTML,
)

from src.utils import (
    handle_consolidated_md,
    get_file_order,
    int_to_letter,
    p_warning,
    p_error,
    p_label,
)
from src.constants import MAX_HEADING_LEVEL

files_with_references = [NORMATIVE_REF_FILE, INFORMATIVE_REF_FILE]


# region Helpers
def undo_prettier_formatting(text: str) -> str:
    """Undo any formatting changes made by Prettier to ensure the Markdown is in a more raw format for processing."""

    def fix_notes_and_examples(text: str) -> str:
        if text.startswith("> > >"):
            text = text.replace("> > >", ">>>")
        return text

    # Remove spaces before and after colons in headings
    new_lines = []
    lines = text.split("\n")

    for line in lines:
        new_line = line

        # Fix notes and examples
        new_line = fix_notes_and_examples(new_line)

        new_lines.append(new_line)

    new_text = "\n".join(new_lines)

    return new_text


def run_format_checks(filename: str, file_lines: list[str]):
    """Runs various checks on the Markdown file contents to ensure they are properly formatted. If any improper formatting is detected, display any fatal errors or warnings as necessary."""

    def check_divs():
        """
        ### Display an error and exit when...
        - An opening does not have a closing

        ### Display a warning when...
        - The number of openings and number of closings do not match
        - Find a closing without a corresponding opening, this is likely meant to be an opening and needs metadata
        """
        i = 0
        in_div = False
        in_div_no_metadata = (
            False  # For if/when a div is found that doesn't have any class
        )
        start_line_num = (
            0  # For keeping track of the line number at which the latest div was opened
        )

        # Keep track of numbers of div starts and div ends
        num_div_start = 0
        num_div_end = 0

        while i < len(file_lines):
            line = file_lines[i].replace("\n", "")
            line_num = i + 1

            bad_div_delin_match = re.match(BAD_DIV_DELINEATOR_REGEX, line)
            if bad_div_delin_match and line.find(":::") == -1:
                # This div delineator doesn't have exactly three colons `:::`
                print(
                    p_error(
                        f"{p_label(filename)}:{p_label(line_num)}: Improperly formatted div delineator in line. Line: {p_label(line)}"
                    )
                )
                raise Exception("DIV_DELINEATOR_ERROR")

            start_match = re.match(DIV_START_REGEX, line)
            num_div_start += 1 if start_match else num_div_start

            if start_match:
                in_div_no_metadata = False  # Set this to false in case it was true from a previous div without metadata
                if in_div:
                    # The previous div wasn't closed, print error and quit
                    print(
                        p_error(
                            f"{p_label(filename)}:{p_label(start_line_num)}: No end tag found for div starting at this line"
                        )
                    )
                    raise Exception("DIV_DELINEATOR_ERROR")
                else:
                    # A normal div opener
                    in_div = True

                start_line_num = line_num
                i += 1
                continue

            end_match = re.match(DIV_END_REGEX, line)
            num_div_end += 1 if end_match else num_div_end

            if end_match:
                if not in_div and not in_div_no_metadata:
                    # This should open a div, but it doesn't have a class assigned to it
                    print(
                        p_warning(
                            f"{p_label(filename)}:{p_label(line_num)}: The delineator at this line seems to open a div, this div or one before it may not be correctly structured."
                        )
                    )
                    in_div_no_metadata = True

                elif not in_div and in_div_no_metadata:
                    # The closing to a classless div
                    in_div_no_metadata = False

                in_div = False
                i += 1
                continue

            i += 1

    def check_notes_and_examples():
        """
        Display an error and exit when the [!note] or [!tip] tags are followed by some text that is not "NOTE" or "EXAMPLE" respectively.
        """
        note_regex = r"^>>> \[!note\]"
        note_in_table_regex = r"^\| >>> \[!note\]"
        example_regex = r"^>>> \[!tip\]"
        note_allowed_text = r"^>>> \[!note\]( NOTE(\s\d+)?:)?$"
        note_in_table_allowed_text = r"^\| >>> \[!note\](( NOTE(\s\d+)?:)?\s*\|)?$"
        example_allowed_text = r"^>>> \[!tip\]( EXAMPLE(\s\d+)?:)?$"

        for i, line in enumerate(file_lines):
            line_num = i + 1
            if re.match(note_regex, line):
                if re.match(note_allowed_text, line):
                    continue
                print(f"line: {line}")
                print(
                    p_error(
                        f"{p_label(filename)}:{p_label(line_num)}: NOTE with unexpected text found. Please ensure the NOTE tag is either empty or is followed by 'NOTE', an optional number and a colon."
                    )
                )
                raise Exception("NOTE_NUMBERING_ERROR")
            if re.match(note_in_table_regex, line):
                if re.match(note_in_table_allowed_text, line):
                    continue
                print(f"line: {line}")
                print(
                    p_error(
                        f"{p_label(filename)}:{p_label(line_num)}: NOTE with unexpected text found in table. Please ensure the NOTE tag is either empty or is followed by 'NOTE', an optional number and a colon. Also, since this is in a table, ensure the line ends with a pipe '|' character without any other text after it. Finally, NOTES in tables can only be in cells that span over all columns."
                    )
                )
                raise Exception("NOTE_NUMBERING_ERROR")
            if re.match(example_regex, line):
                if re.match(example_allowed_text, line):
                    continue
                print(f"line: {line}")
                print(
                    p_error(
                        f"{p_label(filename)}:{p_label(line_num)}: EXAMPLE with unexpected text found. Please ensure the EXAMPLE tag is either empty or is followed by 'EXAMPLE', an optional number and a colon."
                    )
                )
                raise Exception("EXAMPLE_NUMBERING_ERROR")

    check_divs()
    check_notes_and_examples()


def remove_ignore_prettier_statements(text: str) -> str:
    """Remove any existing <!-- prettier-ignore --> statements from the text to avoid duplication"""
    new_lines = []
    for line in text.split("\n"):
        if (
            line.strip() != "<!-- prettier-ignore-start -->"
            and line.strip() != "<!-- prettier-ignore-end -->"
        ):
            new_lines.append(line)

    return "\n".join(new_lines)


def add_divs_to_images_tables(text: str) -> str:
    """Add divs around images and their captions, and tables captions to the ones defined using the ETSI guidelines."""
    file_lines = text.split("\n")
    new_file_lines = []
    TABLE_CAPTION_REGEX = r"^\*\*Table"
    IMAGE_CAPTION_REGEX = r"^\*\*Figure"
    IMAGE_DEF_REGEX = r"^!\[.*\]\(.*\)"

    for line in file_lines:
        if re.match(IMAGE_DEF_REGEX, line):
            # If the line is an image definition, add divs around it
            new_file_lines.append("::: FL")
            new_file_lines.append(line)
            new_file_lines.append(":::")
        elif re.match(IMAGE_CAPTION_REGEX, line):
            # If the line is an image caption, add divs around it
            new_file_lines.append("::: TF")
            new_file_lines.append(line.replace("**", ""))
            new_file_lines.append(":::")
        elif re.match(TABLE_CAPTION_REGEX, line):
            # If the line is a table caption, add divs around it
            new_file_lines.append("::: TH")
            new_file_lines.append(line.replace("**", ""))
            new_file_lines.append(":::")
        else:
            new_file_lines.append(line)

    return "\n".join(new_file_lines) + "\n"


def handle_less_than_greater_than_text(file_contents: str):
    """Replace `<` and `>` with `&lt;` and `&gt;` respectively and wrap the whole section in single code ticks to allow the text to render in the HTML"""
    regex = r"\<(?!img\b|span\b|sup|/sup|mark|/mark|br\b|/br\b|\b)(.+?)\>"
    replace = r"`&lt;\1&gt;`"
    table_regex = rf"\|([^|\n]*?{regex}[^|\n]*?)\|"

    def replace_in_table(match: re.Match):
        cell_body = match.group(1)
        intended_length = len(cell_body)

        cell_body = re.sub(regex, replace, cell_body)

        new_cell = f"|{cell_body[:intended_length]}|"
        return new_cell

    while True:
        file_contents, count = re.subn(table_regex, replace_in_table, file_contents)
        if (
            count == 0
        ):  # Break out of the loop once there aren't any more substitutions to make
            break

    file_contents = re.sub(regex, replace, file_contents)

    return file_contents


def add_ids_to_headings(file_contents: str):
    """Add HTML IDs to all headings in the document."""

    def extract_id_from_heading(heading_text: str) -> str:
        """Extract ID from heading text using the same logic as preprocessing.py"""
        annex_regex = r"^Annex\s+([A-Z])(?:\s+\([\w]+\):|\s*:)?\s"
        clause_number_regex = r"^([A-Z]?\.?\d+(\.\d+)*)\s"

        if re.match(annex_regex, heading_text):
            match = re.match(annex_regex, heading_text)
            return match.group(1)  # Extracts only the letter (A, B, C, etc.)
        elif re.match(clause_number_regex, heading_text):
            match = re.match(clause_number_regex, heading_text)
            return match.group(1)  # Extracts the clause number
        else:
            # Generate a fallback ID from the heading text
            return re.sub(r"[^a-zA-Z0-9]", "-", heading_text.strip()).lower()

    for level in range(1, MAX_HEADING_LEVEL):
        regex = rf"^(#{{{level}}} (.+))$"

        def replacement(match):
            full_heading = match.group(1)
            heading_text = match.group(2)
            heading_id = extract_id_from_heading(heading_text)
            return rf"{full_heading} {{#{heading_id}}}"

        file_contents = re.sub(regex, replacement, file_contents, flags=re.MULTILINE)

    return file_contents


def add_empty_lines_in_notes_and_examples(file_contents: str):
    """Ensure there is an empty line after the NOTE and EXAMPLE tags to ensure proper rendering. This is required because Pandoc would otherwise merge the note/example tag line with the first line of the note/example."""
    file_lines = file_contents.split("\n")
    new_file_lines = []
    i = 0
    while i < len(file_lines):
        line = file_lines[i]

        # opening of a note or example
        if (
            line.startswith(">>> [!note]")
            or line.startswith(">>> [!tip]")
            or line.startswith("| >>> [!note]")
        ):
            new_file_lines.append(line)
            # Check if the next line exists and is not empty
            if i + 1 < len(file_lines) and file_lines[i + 1].strip() != "":
                if not line.startswith("| >>> [!note]"):
                    new_file_lines.append(
                        ""
                    )  # Add an empty line only for notes/examples outside tables
                else:
                    if not line.startswith("+") and not line.endswith("+"):
                        line_length = (
                            len(line) - 2
                        )  # Subtract 2 for the "|" at the start and end
                        new_file_lines.append(
                            "|" + " " * line_length + "|"
                        )  # Add an empty line

        # closing of a note or example
        elif line.find(">>>") != -1 or line.find("| >>>") != -1:
            # check before the line
            line_before = file_lines[i - 1] if i > 0 else ""
            empty_line_regex = r"^\s*$"
            empty_table_row_regex = r"^\|\s*\|$"
            if not re.match(
                empty_line_regex, line_before
            ) and not line_before.startswith("| "):
                new_file_lines.append(
                    ""
                )  # Add an empty line before any other blockquote
            elif not re.match(empty_table_row_regex, line) and line_before.startswith(
                "| "
            ):
                line_length = (
                    len(line) - 2
                )  # Subtract 2 for the "|" at the start and end
                new_file_lines.append(
                    "|" + " " * line_length + "|"
                )  # Add an empty line before any other blockquote in a table

            new_file_lines.append(line)

            # check after the line
            if not line.startswith("| >>>"):  # we are not in a table
                new_file_lines.append(
                    ""
                )  # Add an empty line after any other blockquote
            elif line.startswith("| >>>"):
                if not line.startswith("+-") and not line.startswith("+="):
                    line_length = (
                        len(line) - 2
                    )  # Subtract 2 for the "|" at the start and end
                    new_file_lines.append(
                        "|" + " " * line_length + "|"
                    )  # Add an empty line
        else:
            new_file_lines.append(line)
        i += 1
    return "\n".join(new_file_lines) + "\n"


# Used to keep track of clause numbers across multiple levels when auto-numbering
clauses_counters = [0] * MAX_HEADING_LEVEL
clauses_counters[0] = 3  # first 3 clauses are taken by mandatory files
annexes_counters = [0] * MAX_HEADING_LEVEL
example_counter = 0
note_counter = 0
note_in_table_counter = 0
figure_counter = 0
table_counter = 0


def auto_number_content(
    file_contents: str, content_type: Literal["clauses", "annexes"]
):
    global example_counter, note_counter, note_in_table_counter

    def auto_number_heading(line: str):
        global clauses_counters, annexes_counters, figure_counter, table_counter
        new_heading = ""
        new_line = line
        is_annex = content_type == "annexes"
        if is_annex and line.startswith("# Annex"):
            annexes_counters[0] += 1
            # set all lower levels to 0
            for j in range(1, MAX_HEADING_LEVEL):
                annexes_counters[j] = 0
            match = re.match(r"^# Annex ([A-Z])(?:\s+.*)?$", line)
            if match:
                new_heading = match.group(1)
                new_line = match.group(0)  # keep the line as is
            else:
                annex_letter = int_to_letter(annexes_counters[0])
                new_heading = annex_letter
                new_line = line.replace("Annex", f"Annex {annex_letter}")
        else:  # it is a clause of a regular file or a sub-clause of an annex
            match = re.match(r"^(#+) (.+)$", line)
            if match:
                level = len(match.group(1))
                if is_annex:
                    annexes_counters[level - 1] += 1
                    # set all lower levels to 1
                    for j in range(level, MAX_HEADING_LEVEL):
                        annexes_counters[j] = 0
                else:
                    clauses_counters[level - 1] += 1
                    # set all lower levels to 1
                    for j in range(level, MAX_HEADING_LEVEL):
                        clauses_counters[j] = 0
                figure_counter = 0
                table_counter = 0

                # check if we have an hardcoded clause number
                existing_number = re.match(
                    r"^(?:\d+|[A-Za-z])(?:\.\d+)*\s+", match.group(2)
                )

                if not existing_number:  # user didn't write a clause number
                    # create a string with all heading counters up to the level
                    if is_annex:
                        annex_letter = int_to_letter(annexes_counters[0])
                        heading_string = (
                            annex_letter
                            + "."
                            + ".".join(str(x) for x in annexes_counters[1:level])
                        )
                    else:
                        heading_string = ".".join(
                            str(x) for x in clauses_counters[:level]
                        )
                    new_heading = heading_string
                    new_line = f"{match.group(1)} {heading_string} {match.group(2)}"
                else:
                    new_heading = existing_number.group(0).strip()
                    new_line = match.group(0)  # keep the line as is
        return new_line, new_heading

    def auto_number_example(line: str) -> str:
        global example_counter
        new_line = line
        example_counter += 1
        if "EXAMPLE" not in line:
            if (
                example_counter != 1
            ):  # if it is one the number can be omitted, need to check later
                new_line = line.replace(
                    ">>> [!tip]", f">>> [!tip] EXAMPLE {example_counter}:[]{{.remove-number}}"
                )
        return new_line

    def auto_number_note(line: str) -> str:
        global note_counter
        new_line = line
        note_counter += 1
        if "NOTE" not in line:
            if (
                note_counter != 1
            ):  # if it is one the number can be omitted, need to check later
                new_line = line.replace(
                    ">>> [!note]", f">>> [!note] NOTE {note_counter}:[]{{.remove-number}}"
                )
        return new_line

    def auto_number_figure(line: str) -> str:
        global figure_counter
        new_line = line
        figure_counter += 1
        match = re.search(r"Figure:", line)
        if match:
            figure_number = f"{previous_heading}-{figure_counter}"
            new_line = line.replace("Figure:", f"Figure {figure_number}:[]{{.remove-number}}")
        return new_line

    def auto_number_table(line: str) -> str:
        global table_counter
        new_line = line
        table_counter += 1
        match = re.search(r"Table:", line)
        if match:
            table_number = f"{previous_heading}-{table_counter}"
            new_line = line.replace("Table:", f"Table {table_number}:[]{{.remove-number}}")
        return new_line

    def auto_number_note_in_table(line: str) -> str:
        global note_in_table_counter
        new_line = line
        note_in_table_counter += 1
        if "NOTE" not in line:
            if (
                note_in_table_counter != 1
            ):  # if it is one the number can be omitted, need to check later
                new_text = f"| >>> [!note] NOTE {note_in_table_counter}:[]{{.remove-number}}"
                text_to_replace = "| >>> [!note]"
                diff_in_length = len(new_text) - len(text_to_replace)
                # ensure we keep the table formatting by adding spaces at the end of the line if needed
                if diff_in_length > 0:
                    text_to_replace = text_to_replace + " " * diff_in_length
                new_line = line.replace(text_to_replace, new_text)
        return new_line

    # take line and line number and replace the line number
    lines = file_contents.splitlines()
    # required to keep track of the previous line for figures and tables
    previous_line = ""
    previous_heading = ""
    first_example_line_index = -1
    first_note_line_index = -1
    first_note_in_table_line_index = -1
    for i, line in enumerate(lines):
        new_line = line

        if line.startswith("#"):
            new_line, new_heading = auto_number_heading(new_line)
            previous_heading = new_heading

            if (
                example_counter >= 1
                and first_example_line_index != -1
                and "EXAMPLE" not in lines[first_example_line_index]
            ):
                lines[
                    first_example_line_index
                ] += f" EXAMPLE{' 1' if example_counter > 1 else ''}:[]{{.remove-number}}"
            example_counter = 0
            first_example_line_index = -1

            if (
                note_counter >= 1
                and first_note_line_index != -1
                and "NOTE" not in lines[first_note_line_index]
            ):
                lines[
                    first_note_line_index
                ] += f" NOTE{' 1' if note_counter > 1 else ''}:[]{{.remove-number}}"
            note_counter = 0
            first_note_line_index = -1

        elif line.startswith(">>> [!tip]"):
            new_line = auto_number_example(new_line)
            if example_counter == 1:
                first_example_line_index = i

        elif line.startswith(">>> [!note]"):
            new_line = auto_number_note(new_line)
            if note_counter == 1:
                first_note_line_index = i

        elif previous_line.startswith("::: TF"):
            new_line = auto_number_figure(new_line)

        elif previous_line.startswith("::: TH"):
            new_line = auto_number_table(new_line)

            if note_in_table_counter >= 1 and first_note_in_table_line_index != -1:
                note_string = (
                    f"| >>> [!note] NOTE{' 1' if note_in_table_counter > 1 else ''}:[]{{.remove-number}}"
                )
                note_string_length = len(note_string)
                text_to_be_replaced = "| >>> [!note]"
                text_to_be_replaced_length = len(text_to_be_replaced)
                diff_in_length = note_string_length - text_to_be_replaced_length
                if diff_in_length > 0:
                    text_to_be_replaced = text_to_be_replaced + " " * diff_in_length
                    lines[first_note_in_table_line_index] = lines[
                        first_note_in_table_line_index
                    ].replace(text_to_be_replaced, note_string)
            note_in_table_counter = 0
            first_note_in_table_line_index = -1

        elif line.startswith("| >>> [!note]"):
            new_line = auto_number_note_in_table(new_line)
            if note_in_table_counter == 1:
                first_note_in_table_line_index = i

        lines[i] = new_line
        previous_line = line

    ### We need to run again the logic where we add the number in examples and notes since we might not have done it for all cases (it triggers on specific points, and if it happens the element is in the last heading/table it may be skipped)

    if (
        example_counter >= 1
        and first_example_line_index != -1
        and "EXAMPLE" not in lines[first_example_line_index]
    ):
        lines[
            first_example_line_index
        ] += f" EXAMPLE{' 1' if example_counter > 1 else ''}:[]{{.remove-number}}"

    if (
        note_counter >= 1
        and first_note_line_index != -1
        and "NOTE" not in lines[first_note_line_index]
    ):
        lines[first_note_line_index] += f" NOTE{' 1' if note_counter > 1 else ''}:[]{{.remove-number}}"

    if note_in_table_counter >= 1 and first_note_in_table_line_index != -1:
        note_string = f"| >>> [!note] NOTE{' 1' if note_in_table_counter > 1 else ''}:[]{{.remove-number}}"
        note_string_length = len(note_string)
        text_to_be_replaced = "| >>> [!note]"
        text_to_be_replaced_length = len(text_to_be_replaced)
        diff_in_length = note_string_length - text_to_be_replaced_length
        if diff_in_length > 0:
            text_to_be_replaced = text_to_be_replaced + " " * diff_in_length
            lines[first_note_in_table_line_index] = lines[
                first_note_in_table_line_index
            ].replace(text_to_be_replaced, note_string)

    file_contents = "\n".join(lines) + "\n"
    return file_contents


def add_ids_to_references(file_contents: str, filename: str):
    """Ensure any characters that need to be escaped are escaped."""

    def handle_references(file_contents: str, filename: str):
        """Make sure references are correctly escaped."""
        # Pattern for informative references with "i." prefix
        REF_REGEX_I = r"^\[(i\.[A-Za-z0-9]+)\]"

        # Pattern for normative references with "n." prefix
        REF_REGEX_N = r"^\[(n\.[A-Za-z0-9]+)\]"

        if (
            filename.replace(".md", "") in files_with_references
        ):  # references clauses, add span with ids

            with open(REFERENCE_MAPPING_MD_TO_HTML, "r") as ref_file:
                reference_mapping = json.load(ref_file)

            normative_index = 1
            informative_index = 1

            def replace_informative_ref(match: re.Match) -> str:
                nonlocal informative_index
                ref_id = match.group(1)
                new_ref = f"i.{informative_index}"
                reference_mapping[ref_id] = new_ref
                informative_index += 1
                return f'<span id="{new_ref}" />[{new_ref}]'

            def replace_normative_ref(match: re.Match) -> str:
                nonlocal normative_index
                ref_id = match.group(1)
                new_ref = f"n.{normative_index}"
                reference_mapping[ref_id] = new_ref
                normative_index += 1
                return f'<span id="{new_ref}" />[{new_ref}]'

            file_contents = re.sub(
                REF_REGEX_I,
                replace_informative_ref,
                file_contents,
                flags=re.MULTILINE,
            )
            file_contents = re.sub(
                REF_REGEX_N,
                replace_normative_ref,
                file_contents,
                flags=re.MULTILINE,
            )

            with open(REFERENCE_MAPPING_MD_TO_HTML, "w") as ref_file:
                json.dump(reference_mapping, ref_file)

        return file_contents

    file_contents = handle_references(file_contents, filename)

    return file_contents


# endregion
def preprocess(
    src: str, src_type: str, consolidated_md_path: str, file_order_json: str
):
    """
    ### Description
    Preprocesses Markdown files to prepare them for conversion to HTML by applying various transformations:

    1. Performs format validation checks on divs, notes, and examples
    2. Removes any existing prettier-ignore statements
    3. Adds appropriate divs around images, tables, and their captions
    4. Auto-numbers clauses, annexes, examples, notes, figures, and tables
    5. Adds IDs to references for proper linking
    6. Handles special characters like '<' and '>' to ensure proper rendering
    7. Adds IDs to headings for navigation and cross-referencing
    8. Ensures proper formatting of notes and examples with empty lines
    9. Consolidates all preprocessed files into a single Markdown file

    ### Arguments
    - `src`: The absolute or relative path of the directory containing the source Markdown files
    - `src_type`: The source file type, `md`
    - `consolidated_md_path`: The path at which the consolidated Markdown file will be created
    - `file_order_json`: Path to JSON file specifying custom order of clauses and annexes

    ### Returns
    - A dictionary mapping filenames to their numeric/alphabetic positions in the document
    """
    filename_numbers_mapping = {}
    clauses = DEFAULT_CLAUSES
    annexes = DEFAULT_ANNEXES

    # create REFERENCE_MAPPING_MD_TO_HTML file locally if it doesn't exist
    with get_timer().section("Preprocessing: 1 - Creating reference mapping file"):
        if not os.path.exists(REFERENCE_MAPPING_MD_TO_HTML):
            with open(REFERENCE_MAPPING_MD_TO_HTML, "w") as ref_file:
                json.dump({}, ref_file, indent=4)
    with get_timer().section("Preprocessing: 2 - Preprocessing Markdown files"):
        if file_order_json:
            with open(file_order_json, "r") as file:
                json_data = json.load(file)
                clauses = json_data.get("clauses")
                annexes = json_data.get("annexes")

        files, clauses_filenames, annexes_filenames = get_file_order(
            src, clauses, annexes
        )
        files = [f"{filename}.md" for filename in files]
        clauses_filenames = [f"{filename}.md" for filename in clauses_filenames]
        annexes_filenames = [f"{filename}.md" for filename in annexes_filenames]
        preprocessed_filenames = []
    with get_timer().section("Preprocessing: 3 - Processing individual files"):
        for filename in files:
            filename_without_extension = filename[:-3]  # Remove .md extension
            if filename.endswith(src_type) and filename != "consolidated.md":
                input_path = os.path.join(src, filename)
                try:
                    with open(input_path, "r", encoding="utf-8") as file:
                        text = file.read()

                    text = undo_prettier_formatting(text)
                    run_format_checks(filename, text.splitlines())

                    text = remove_ignore_prettier_statements(text)

                    text = add_divs_to_images_tables(text)

                    if filename in clauses_filenames:
                        text = auto_number_content(text, "clauses")
                        filename_numbers_mapping[filename_without_extension] = (
                            clauses_counters[0]
                        )
                    elif filename in annexes_filenames:
                        text = auto_number_content(text, "annexes")
                        filename_numbers_mapping[filename_without_extension] = (
                            int_to_letter(annexes_counters[0]).lower()
                        )
                    text = add_ids_to_references(text, filename)
                    text = handle_less_than_greater_than_text(text)
                    text = add_ids_to_headings(text)
                    text = add_empty_lines_in_notes_and_examples(text)
                    if filename_without_extension in REFS:
                        text = text.replace("::: REFS", "::: EX")

                    new_filename = re.sub(
                        r"([\w-]+?).md", r"--preprocessed--\1.md", filename
                    )  # Ensure file order is preserved by keeping the number in front
                    output_path = os.path.join(src, new_filename)
                    with open(output_path, "w", encoding="utf-8") as file:
                        file.write(text)
                    preprocessed_filenames.append(new_filename)
                except Exception as e:
                    # print(f"Error: {e}")
                    # print(
                    #     f"Warning: Could not preprocess {input_path}. It may not be a valid UTF-8 text file or is missing."
                    # )
                    if (
                        e.args[0] == "DIV_DELINEATOR_ERROR"
                        or e.args[0] == "NOTE_NUMBERING_ERROR"
                        or e.args[0] == "EXAMPLE_NUMBERING_ERROR"
                    ):
                        # delete all files that start with --preprocessed--
                        for f in os.listdir(src):
                            if f.startswith("--preprocessed--"):
                                os.remove(os.path.join(src, f))
                        sys.exit(1)
                    p_warning(f"Warning: Could not preprocess {input_path}: {e}")
    with get_timer().section("Preprocessing: 4 - Creating consolidated Markdown file"):
        handle_consolidated_md(
            "create", src, consolidated_md_path, preprocessed_filenames
        )

    return filename_numbers_mapping
