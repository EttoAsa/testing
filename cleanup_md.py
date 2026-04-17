import argparse
import os
import subprocess
import json
import sys
import re
from src.utils import try_reformat_json

# from src.to_md.preprocessing import run_format_checks()
EXAMPLE_PREFIX = ">>> [!tip]"
NOTE_PREFIX = ">>> [!note]"
EXAMPLE_NOTE_POSTFIX = ">>>"
BLOCK_CODE_PREFIX = "```"
BLOCK_CODE_POSTFIX = "```"
TABLE_PREFIX = "::: TAL"
IMAGE_PREFIX = "::: FL"
LABLE_PREFIX = "::: TF"
TABLE_HEADER_PREFIX = "::: TH"
GENERIC_CUSTOM_BLOCK_PREFIX = "::: "
CUSTOM_BLOCK_POSTFIX = ":::"  # This is a common postfix for custom blocks like tables, images, labels, etc.

PRETTIER_IGNORE_START_COMMENT = "<!-- prettier-ignore-start -->"
PRETTIER_IGNORE_END_COMMENT = "<!-- prettier-ignore-end -->"


def run_prettier_on_file(file_path):
    try:
        subprocess.run(
            [
                "npx",
                "prettier",
                file_path,
                "--write",
                "--prose-wrap",
                "always",
            ],
            check=True,
        )
    except FileNotFoundError:
        print("Error: 'npx' not found. Make sure Node.js/npm are installed.")
        return False
    except subprocess.CalledProcessError as error:
        print(
            f"Error: Prettier failed with exit code {error.returncode} on {file_path}."
        )
        return False
    return True


def remove_prettier_ignore_comments_not_from_this_script(md_lines):
    """
    Removes the lines with prettier ignore comments from the markdown content that were not added by this script.
    Prevently added prettier ignore comments might break the formatting of the markdown file.
    """
    cleaned_lines = []
    for line in md_lines:
        if not line.startswith(PRETTIER_IGNORE_START_COMMENT) and not line.startswith(
            PRETTIER_IGNORE_END_COMMENT
        ):
            cleaned_lines.append(line)
    return cleaned_lines


def remove_prettier_ignore(md_lines):
    """
    Removes the lines with prettier ignore comments from the markdown content.
    Clean up the markdown after prettier has been run in the markdown file.
    """
    cleaned_lines = []
    i = 0
    while i < len(md_lines):
        line = md_lines[i]
        if not line.startswith(PRETTIER_IGNORE_START_COMMENT) and not line.startswith(
            PRETTIER_IGNORE_END_COMMENT
        ):
            cleaned_lines.append(line)
            i += 1
        else:
            if cleaned_lines and cleaned_lines[-1] == "\n":
                cleaned_lines.pop()
            if i + 1 < len(md_lines) and md_lines[i + 1] == "\n":
                i += 2
            else:
                i += 1
    return cleaned_lines


def add_prettier_ignore_comment(lines, comment, index):
    """
    Adds a prettier ignore comment at the specified index in the lines list, ensuring it is surrounded by blank lines.
    """
    lines.insert(index, "\n")
    lines.insert(index + 1, comment)
    lines.insert(index + 2, "\n")
    return index + 3


def add_prettier_ignore(md_lines):
    """
    Adds prettier ignore comments to markdown content.
    """
    table_beginning = None
    table_ending = None
    def add_prettier_ignore_on_standalone_tables(lines):
        """
        Add prettier ignore comments before and after table blocks not already wrapped by prettier comments.
        """
        currently_in_table_block = False
        currently_in_prettier_ignore_block = False
        table_type = None
        i = 0
        table_beginning = None
        table_ending = None
        while i < len(lines):
            line = lines[i]

            if line.strip() == PRETTIER_IGNORE_START_COMMENT.strip():
                currently_in_prettier_ignore_block = True
                i += 1
                continue
            if (
                currently_in_prettier_ignore_block
                and line.strip() == PRETTIER_IGNORE_END_COMMENT.strip()
            ):
                currently_in_prettier_ignore_block = False
                i += 1
                continue

            if currently_in_prettier_ignore_block:
                i += 1
                continue

            if not currently_in_table_block:
                if is_ascii_table_line(line):
                    i = add_prettier_ignore_comment(
                        lines, PRETTIER_IGNORE_START_COMMENT, i
                    )
                    currently_in_table_block = True
                    table_type = "ascii"
                    table_beginning = i
                    i += 1
                    continue

                stripped = line.strip()
                if stripped.startswith("|") and stripped.endswith("|"):
                    if i + 1 < len(lines) and is_markdown_table_separator(lines[i + 1]):
                        i = add_prettier_ignore_comment(
                            lines, PRETTIER_IGNORE_START_COMMENT, i
                        )
                        currently_in_table_block = True
                        table_type = "markdown"
                        i += 1
                        continue

                i += 1
            else:
                should_end_table = False
                if table_type == "ascii":
                    if not is_ascii_table_line(line):
                        should_end_table = True
                elif table_type == "markdown":
                    stripped = line.strip()
                    if not (stripped.startswith("|") and stripped.endswith("|")):
                        should_end_table = True

                if should_end_table:
                    table_ending = i
                    i = add_prettier_ignore_comment(
                        lines, PRETTIER_IGNORE_END_COMMENT, i
                    )
                    if table_type == "ascii":
                        new_table = simplify_table(lines[table_beginning:table_ending])
                        if not new_table is None:
                            lines[table_beginning:table_ending] = new_table
                    table_beginning = None
                    table_ending = None
                    currently_in_table_block = False
                    table_type = None
                    i += 1
                else:
                    i += 1

        if currently_in_table_block:
            table_ending = len(lines)
            add_prettier_ignore_comment(
                lines, PRETTIER_IGNORE_END_COMMENT, table_ending
            )
            if table_type == "ascii" and table_beginning is not None:
                new_table = simplify_table(lines[table_beginning:table_ending])
                if not new_table is None:
                    lines[table_beginning:table_ending] = new_table

        return lines

    currently_in_prettier_ignore_block = False
    post_fix_expected = ""
    i = 0

    while i < len(md_lines):
        line = md_lines[i]
        if table_beginning is not None and table_ending is not None:
            if line.strip() == table_ending.strip():
                table_beginning = None
                table_ending = None
        if line.strip() == PRETTIER_IGNORE_START_COMMENT.strip():
            currently_in_prettier_ignore_block = True
            i += 1
            continue
        if (
            currently_in_prettier_ignore_block
            and line.strip() == PRETTIER_IGNORE_END_COMMENT.strip()
        ):
            currently_in_prettier_ignore_block = False
            i += 1
            continue

        if currently_in_prettier_ignore_block:
            i += 1
            continue

        if not post_fix_expected:
            if line.startswith(EXAMPLE_PREFIX) or line.startswith(NOTE_PREFIX):
                i = add_prettier_ignore_comment(
                    md_lines, PRETTIER_IGNORE_START_COMMENT, i
                )
                post_fix_expected = EXAMPLE_NOTE_POSTFIX
                i += 1
            elif line.startswith(BLOCK_CODE_PREFIX):
                i = add_prettier_ignore_comment(
                    md_lines, PRETTIER_IGNORE_START_COMMENT, i
                )
                post_fix_expected = BLOCK_CODE_POSTFIX
                i += 1
            elif line.startswith(TABLE_PREFIX):
                i = add_prettier_ignore_comment(
                    md_lines, PRETTIER_IGNORE_START_COMMENT, i
                )
                post_fix_expected = CUSTOM_BLOCK_POSTFIX
                i += 1
                table_beginning = i
            else:
                i += 1
        elif line.strip() == post_fix_expected.strip():
            table_ending = i
            i = add_prettier_ignore_comment(md_lines, PRETTIER_IGNORE_END_COMMENT, i)
            post_fix_expected = ""
            new_table = simplify_table(md_lines[table_beginning:table_ending])
            if not new_table is None:
                md_lines[table_beginning:table_ending] = new_table
            table_beginning = None
            table_ending = None
            i += 1
        else:
            i += 1

    md_lines = add_prettier_ignore_on_standalone_tables(md_lines)
    return md_lines


def use_md_image_syntax(md_lines):
    """
    Converts image syntax from custom block format to standard markdown image syntax.
    """
    found_image_tag = False
    i = 0
    while i < len(md_lines):
        line = md_lines[i]
        if line.strip().startswith(IMAGE_PREFIX):
            found_image_tag = True
            md_lines[i] = "\n"
        elif found_image_tag and line.strip() == CUSTOM_BLOCK_POSTFIX.strip():
            found_image_tag = False
            md_lines.pop(i)
        elif line.strip().startswith("<img") and line.strip().endswith(">"):
            line = line.strip()
            # Extract the src attribute value
            src_start = line.find('src="') + len('src="')
            src_end = line.find('"', src_start)
            src = line[src_start:src_end]
            # Extract the height attribute value
            height_start = line.find('height="') + len('height="')
            height_end = line.find('"', height_start)
            height = line[height_start:height_end]
            if height and height.endswith("px"):
                height = height[:-2]
            if height and not height.isdigit():
                height = None
            # Extract the width attribute value
            width_start = line.find('width="') + len('width="')
            width_end = line.find('"', width_start)
            width = line[width_start:width_end]
            if width and width.endswith("px"):
                width = width[:-2]
            if width and not width.isdigit():
                width = None
            # Extract the alt text if present
            alt_text = ""
            alt_start = line.find('alt="')
            if alt_start != -1:
                alt_start += len('alt="')
                alt_end = line.find('"', alt_start)
                alt_text = line[alt_start:alt_end]
            if alt_text:
                alt_text = alt_text.strip()
            # Convert to markdown image syntax
            md_image_syntax = f"![]({src})"
            if (alt_text and alt_text != "") or height or width:
                md_image_syntax += "{"
            if alt_text and alt_text != "":
                md_image_syntax += f' alt="{alt_text}"'
            if height and height.isdigit():
                md_image_syntax += f' height="{height}px"'
            if width and width.isdigit():
                md_image_syntax += f' width="{width}px"'
            if (alt_text and alt_text != "") or height or width:
                md_image_syntax += " }"
            md_lines[i] = md_image_syntax + "\n"
        i += 1
    return md_lines


def use_md_label_syntax(md_lines):
    """
    Converts label syntax from custom block format to standard markdown label syntax.
    """
    found_label_tag = False
    i = 0
    label = ""
    while i < len(md_lines):
        line = md_lines[i]
        if line.strip().startswith(LABLE_PREFIX) or line.strip().startswith(
            TABLE_HEADER_PREFIX
        ):
            found_label_tag = True
            md_lines[i] = "\n"
            label = ""
        elif found_label_tag and line.strip() == CUSTOM_BLOCK_POSTFIX.strip():
            found_label_tag = False
            md_lines[i] = f"**{label.strip()}**\n\n"
        elif found_label_tag:
            # stacks the lines of the lable if they are in a multi-line block
            label += line.strip() + " "
            md_lines.pop(i)
            i -= 1
        i += 1
    return md_lines


def is_ascii_table_line(line):
    """
    Check if a line is part of an ASCII art table (with +, -, =, :, |).
    Returns True for border lines (like +----+) or content lines (like | cell |).
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Check if line is a border line like +----+ or +====+ or +:---:+ (with alignment markers)
    if stripped.startswith("+") and stripped.endswith("+"):
        # Border lines contain only +, -, =, : and spaces
        chars = set(stripped)
        if chars <= {"+", "-", "=", ":", " "}:
            return True
    # Check if line is a content line like | content | or contains cell dividers
    if stripped.startswith("|") and ("|" in stripped[1:] or "+" in stripped[1:]):
        return True
    return False


def is_markdown_table_separator(line):
    """
    Check if a line is a markdown table separator like |---|---|
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Must start and end with | and contain only |, -, :, and spaces
    if stripped.startswith("|") and stripped.endswith("|"):
        chars = set(stripped)
        if chars <= {"|", "-", ":", " "}:
            # A real markdown separator must have dashes in every cell section
            parts = stripped.split("|")[1:-1]
            if not parts:
                return False
            for part in parts:
                token = part.strip()
                # Remove optional alignment colons and ensure dashes remain
                token = token.strip(":").strip()
                if not token or any(ch != "-" for ch in token):
                    return False
            return True
    return False


def has_complex_table_structure(non_empty_lines):
    """
    Check if a table has complex structure that cannot be converted to standard markdown.

    Complex tables include:
    - Tables with internal cell dividers (lines like |    +-----+)
    - Tables containing markdown lists (-, *, +, or numbered lists)
    - Tables containing images (markdown ![...] or HTML <img>)

    Returns True if the table has complex structure, False otherwise.
    """
    for line in non_empty_lines:
        stripped = line.strip()
        if stripped.startswith("|"):
            content = stripped[1:]

            # Check for internal row dividers
            if "+---" in content or "+===" in content:
                content_without_spaces = content.replace(" ", "")
                if content_without_spaces.startswith(
                    "+---"
                ) or content_without_spaces.startswith("+==="):
                    return True

            # Check for markdown lists (unordered: -, *, + or ordered: 1., 2., etc.)
            # Split by | to check individual cells
            cells = content.split("|")
            for cell in cells:
                cell_stripped = cell.strip()
                # Check for unordered list markers
                if (
                    cell_stripped.startswith("- ")
                    or cell_stripped.startswith("* ")
                    or cell_stripped.startswith("+ ")
                ):
                    return True
                # Check for ordered list markers (digit followed by period and space)
                if (
                    len(cell_stripped) > 2
                    and cell_stripped[0].isdigit()
                    and ". " in cell_stripped[:4]
                ):
                    return True

            # Check for markdown images: ![alt](url)
            if "![" in content and "](" in content:
                return True

            # Check for HTML images: <img
            if "<img" in content.lower():
                return True

    return False


def simplify_table(table_lines):
    """
    Transforms an ASCII table into a standard markdown table if compatible with the standard markdown format,
    otherwise it leaves it unchanged.
    """
    if not table_lines:
        return None

    non_empty_lines = [line for line in table_lines if line.strip()]

    if not non_empty_lines:
        return None

    for line in non_empty_lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if is_markdown_table_separator(line):
                return None
    has_a_complex_structure = has_complex_table_structure(non_empty_lines)
    if has_a_complex_structure:
        return None

    if all(is_ascii_table_line(line) for line in non_empty_lines):
        logical_rows = []
        current_row_lines = []
        alignments = None  # Will store alignment for each column

        for line in non_empty_lines:
            stripped = line.strip()
            if stripped.startswith("+") and stripped.endswith("+"):
                if ":" in stripped and alignments is None:
                    parts = stripped.split("+")[1:-1]
                    alignments = []
                    for part in parts:
                        part = part.strip()
                        if part.startswith(":") and part.endswith(":"):
                            alignments.append("center")
                        elif part.endswith(":"):
                            alignments.append("right")
                        elif part.startswith(":"):
                            alignments.append("left")
                        else:
                            alignments.append("left")  # default

                if current_row_lines:
                    logical_rows.append(current_row_lines)
                    current_row_lines = []
                continue  # skip border lines

            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [cell.strip() for cell in stripped[1:-1].split("|")]
                current_row_lines.append(cells)

        if current_row_lines:
            logical_rows.append(current_row_lines)

        if not logical_rows:
            return None

        num_columns = len(logical_rows[0][0]) if logical_rows[0] else 0

        if alignments is None:
            alignments = ["left"] * num_columns

        merged_rows = []
        for logical_row in logical_rows:
            if not all(len(line) == num_columns for line in logical_row):
                return None

            merged_cells = []
            for col_idx in range(num_columns):
                cell_contents = [
                    logical_row[line_idx][col_idx]
                    for line_idx in range(len(logical_row))
                ]
                # Join cell contents: use <br> only if next line is empty, otherwise use space
                merged_parts = []
                for idx, content in enumerate(cell_contents):
                    content = content.strip()
                    if content.endswith(" \\"):
                        content = content[:-2].rstrip()
                    if idx == 0:
                        merged_parts.append(content)
                    else:
                        # Check if previous content was empty
                        if cell_contents[idx - 1].strip() == "":
                            # Previous was empty, use <br>
                            merged_parts.append("<br>" + content)
                        else:
                            # Previous had content, use space if current is not empty
                            if content.strip() == "":
                                merged_parts.append("<br>" + content)
                            else:
                                merged_parts.append(" " + content)
                merged_cell = "".join(merged_parts)
                merged_cells.append(merged_cell)
            merged_rows.append(merged_cells)

        # Convert to markdown format
        markdown_table = []
        for i, row in enumerate(merged_rows):
            markdown_table.append("| " + " | ".join(row) + " |\n")
            if i == 0:
                separator_parts = []
                for align in alignments:
                    if align == "center":
                        separator_parts.append(" :---: ")
                    elif align == "right":
                        separator_parts.append(" ---: ")
                    else:
                        separator_parts.append(" --- ")
                markdown_table.append("|" + "|".join(separator_parts) + "|\n")

        table_lines.clear()
        table_lines.extend(markdown_table)
        return table_lines
    else:
        return None

def ensure_spacing_around_lists(md_lines):
    """
    The function add a break line if the list starts with
    dash (-) or a number list (1., 2., etc.).
    """
    new_lines = []
    for i in range(len(md_lines)):
        line = md_lines[i]
        new_lines.append(line)
        
        # it cleans the current line and it checks if it's a list
        current_strip = line.strip()
        is_current_list = current_strip.startswith("- ") or bool(re.match(r'^\d+\.\s', current_strip))

        #Controlling if there's a next line
        if is_current_list and i + 1 < len(md_lines):
            next_strip = md_lines[i+1].strip()
            
            #controlling if the next line is a list
            is_next_list = next_strip.startswith("- ") or bool(re.match(r'^\d+\.\s', next_strip))

            # add a blank line
            if is_next_list:
                new_lines.append("\n")
                
    return new_lines

def spacing_note_example_blocks(md_lines):
    """
    This function checks if there is a break line before and after the special block '>>>'.
    It adds new break lines when needed.
    """
    new_lines = []
    for i, line in enumerate(md_lines):
        stripped = line.strip()

        # Check if the current line starts with an Example or Note prefix
        if stripped.startswith((EXAMPLE_NOTE_POSTFIX, EXAMPLE_PREFIX, NOTE_PREFIX)):
            # Add a blank line before if the previous line is not empty
            if new_lines and new_lines[-1].strip() != "":
                new_lines.append("\n")

            new_lines.append(line)

            # Add a blank line after if the next line is not empty
            if i + 1 < len(md_lines) and md_lines[i + 1].strip() != "":
                new_lines.append("\n")
        else:
            new_lines.append(line)

    return new_lines


def format_json_blocks(md_lines):
    """
    Finds JSON code blocks in markdown (```json ... ```)
    and reformats the JSON content using try_reformat_json().
    """

    result = []
    inside_json = False
    buffer = []

    for line in md_lines:
        stripped = line.strip()

        # Start of JSON block
        if not inside_json and stripped.startswith(BLOCK_CODE_PREFIX + "json"):
            inside_json = True
            buffer = []
            result.append(BLOCK_CODE_PREFIX + "json\n")
            continue

        # End of JSON block
        if inside_json and stripped == BLOCK_CODE_POSTFIX:
            inside_json = False

            raw_json = "\n".join(buffer).strip()

            # NEW: use your advanced JSON formatter
            formatted = try_reformat_json(raw_json)

            # Write formatted JSON back into the markdown
            for l in formatted.split("\n"):
                result.append(l + "\n")

            result.append(BLOCK_CODE_POSTFIX + "\n")
            continue

        # Inside JSON block → accumulate lines
        if inside_json:
            buffer.append(line.rstrip("\n"))
            continue

        # Normal line
        result.append(line)

    return result


def collapse_empty_spaces(md_lines):
    """
    Ensures that between two lines of text there is at most ONE empty line.
    Removes multiple consecutive empty lines.

    """

    result = []
    previous_empty = False

    for line in md_lines:
        if line.strip() == "":

            if not previous_empty:
                result.append(line)
                previous_empty = True
        else:
            result.append(line)
            previous_empty = False
    return result

def check_grid_boundary(stripped, stack, i, file_path):
    """
    Check if the line is a grid table boundary (+---+---+).
    If it is, verify that no blocks are left open in the cell.
    Returns True if the line is a boundary.
    """
    is_grid_boundary = stripped.startswith("+") and "-" in stripped and stripped.endswith("+")
    if is_grid_boundary:
        if stack and stack[-1].get("in_grid"):
            opened_type = stack[-1]["type"]
            opened_line = stack[-1]["line"]
            print(f"CRITICAL ERROR: Grid cell closed at line {i + 1} before '{opened_type}' block (opened at line {opened_line}) was closed in '{file_path}'.")
            sys.exit(1)
        return True
    return False

def extract_line_tokens(stripped):
    """
    Extract tokens from a line.
    If it's a grid row, splits it into individual cells using '|'.
    Returns a tuple: (list_of_tokens, boolean_in_grid_row)
    """
    in_grid_row = stripped.startswith("|") and stripped.endswith("|")
    tokens = []

    if in_grid_row:
        # Remove the first and last pipe of the table row
        inner_content = stripped[1:-1]
        # Split the row column by column
        for cell in inner_content.split("|"):
            clean_cell = cell.strip()
            if clean_cell:
                tokens.append(clean_cell)
    else:
        tokens.append(stripped)

    return tokens, in_grid_row

def try_close_top_block(content, stack):
    """
    Check if the content exactly matches the closing tag of the block currently at the top of the stack.
    Returns True if the block was successfully closed.
    """
    if not stack:
        return False
        
    top = stack[-1]
    is_closed = False
    
    if top["type"] == "TIP_NOTE" and content == EXAMPLE_NOTE_POSTFIX:
        is_closed = True
    elif top["type"] == "CODE" and content == BLOCK_CODE_POSTFIX:
        is_closed = True
    elif top["type"] == "CUSTOM" and content == CUSTOM_BLOCK_POSTFIX:
        is_closed = True
        
    if is_closed:
        stack.pop()
        return True
        
    return False

def try_open_tip_note(content, stack, i, file_path, in_grid_row):
    """
    Check and handle the opening of a TIP or NOTE block (>>> [!tip] / >>> [!note]).
    Returns True if handled.
    """
    if content.startswith(EXAMPLE_PREFIX) or content.startswith(NOTE_PREFIX):
        # Rule: No same-type nesting for TIP_NOTE
        if any(b["type"] == "TIP_NOTE" for b in stack):
            print(f"CRITICAL ERROR: Cannot nest '{content}' inside another TIP/NOTE block at line {i + 1} in '{file_path}'.")
            sys.exit(1)

        # Handle inline blocks (opening and closing on the exact same line)
        if content != EXAMPLE_NOTE_POSTFIX and content.endswith(EXAMPLE_NOTE_POSTFIX):
            return True
        
        stack.append({
            "type": "TIP_NOTE",
            "expected": EXAMPLE_NOTE_POSTFIX,
            "line": i + 1,
            "in_grid": in_grid_row
        })
        return True
        
    return False


def try_open_code_block(content, stack, i, in_grid_row):
    """
    Check and handle the opening of a CODE block (```).
    Returns True if handled.
    """
    if content.startswith(BLOCK_CODE_PREFIX):
        if content != BLOCK_CODE_POSTFIX and content.endswith(BLOCK_CODE_POSTFIX):
            return True
            
        stack.append({
            "type": "CODE",
            "expected": BLOCK_CODE_POSTFIX,
            "line": i + 1,
            "in_grid": in_grid_row
        })
        return True
        
    return False


def try_open_custom_block(content, stack, i, in_grid_row):
    """
    Check and handle the opening of a CUSTOM block (:::).
    Returns True if handled.
    """
    if content.startswith(CUSTOM_BLOCK_POSTFIX):
        if content != CUSTOM_BLOCK_POSTFIX and content.endswith(CUSTOM_BLOCK_POSTFIX):
            return True
            
        stack.append({
            "type": "CUSTOM",
            "expected": CUSTOM_BLOCK_POSTFIX,
            "line": i + 1,
            "in_grid": in_grid_row
        })
        return True
        
    return False


def check_blocks_closed(md_lines, file_path):
    """
    Check that all blocks in the markdown file are properly closed.
    Rules:
    - Different block types CAN be nested (e.g., a Tip can contain a Code block ``` or :::).
    - Same block types CANNOT be nested (a Tip/Note cannot contain another Tip/Note).
    - Grid table cells can contain only [!note] blocks ('| >>> [!note]'), but they must be
      closed ('| >>>') before the grid cell boundary  ('+----').
    """
    stack = []

    for i, line in enumerate(md_lines):
        stripped = line.strip()

        if not stripped:
            continue

        # Grid Boundary Check
        if check_grid_boundary(stripped, stack, i, file_path):
            continue

        # Extract tokens (handles grid cells vs normal lines)
        tokens_to_check, in_grid_row = extract_line_tokens(stripped)

        # Analyze each token
        for content in tokens_to_check:

            if try_close_top_block(content, stack):
                continue

            # Check for orphaned '>>>' (Since '>>>' is strictly a closing tag)
            if content == EXAMPLE_NOTE_POSTFIX:
                print(f"CRITICAL ERROR: Found unexpected or orphaned closing tag '{content}' at line {i + 1} in '{file_path}'.")
                sys.exit(1)

            # Try to open new blocks
            if try_open_tip_note(content, stack, i, file_path, in_grid_row):
                continue
            if try_open_code_block(content, stack, i, in_grid_row):
                continue
            if try_open_custom_block(content, stack, i, in_grid_row):
                continue

    # Check if stack is empty
    if stack:
        top = stack[-1]
        print(f"CRITICAL ERROR: Found unclosed '{top['type']}' block in '{file_path}' starting at line {top['line']} (Expected '{top['expected']}'). Stopping execution.")
        sys.exit(1)

    return True

def are_tips_notes_syntax_valid(md_lines, file_path):
    """
    Validates that >>> [!tip] and >>> [!note] do not have characters or spaces after it,
    unless they match the allowed formats.
    Allowed formats for tip and note:
    - >>> [!tip]            / >>> [!note]
    - >>> [!tip] EXAMPLE    / >>> [!note] NOTE
    - >>> [!tip] EXAMPLE:   / >>> [!note] NOTE:
    - >>> [!tip] EXAMPLE 1  / >>> [!note] NOTE 1
    - >>> [!tip] EXAMPLE 1: / >>> [!note] NOTE 1:
    """

    tip_pattern = r"^" + re.escape(EXAMPLE_PREFIX) + r"(?: EXAMPLE(?: \d+)?:?)?$"
    note_pattern = r"^" + re.escape(NOTE_PREFIX) + r"(?: NOTE(?: \d+)?:?)?$"

    for i, line in enumerate(md_lines):
        l_left = line.lstrip(' \t')
        l_clean = l_left.rstrip('\r\n')
        
        if l_clean.startswith(EXAMPLE_PREFIX):
            if not re.match(tip_pattern, l_clean):
                print(f"CRITICAL ERROR: Invalid format after '{EXAMPLE_PREFIX}' at line {i + 1} in '{file_path}'.")
                return False
        elif l_clean.startswith(NOTE_PREFIX):
            if not re.match(note_pattern, l_clean):
                print(f"CRITICAL ERROR: Invalid format after '{NOTE_PREFIX}' at line {i + 1} in '{file_path}'.")
                return  False
    return True

def run_cleanup(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    content_lines = content.splitlines(keepends=True)
    if not check_blocks_closed(content_lines, file_path):
        return
    content_lines = ensure_spacing_around_lists(content_lines)
    content_lines = spacing_note_example_blocks(content_lines)
    content_lines = remove_prettier_ignore_comments_not_from_this_script(content_lines)
    content_lines = use_md_image_syntax(content_lines)
    if not are_tips_notes_syntax_valid(content_lines, file_path):
        sys.exit(1)
    content_lines = use_md_label_syntax(content_lines)
    content_lines = format_json_blocks(content_lines)
    content_lines = add_prettier_ignore(content_lines)
    if not run_prettier_on_file(file_path):
        return
    content_lines = remove_prettier_ignore(content_lines)
    content_lines = collapse_empty_spaces(content_lines)

    content = ''.join(content_lines)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Updated: {file_path}")


def main():
    parser = argparse.ArgumentParser(description="Cleanup markdown file")
    parser.add_argument(
        "--src", type=str, required=True, help="Path to the markdown file"
    )

    args = parser.parse_args()
    path = args.src

    if os.path.isfile(path):
        if path.endswith(".md"):
            run_cleanup(path)
        else:
            print(f"Error: {path} is not a markdown file.")
    elif os.path.isdir(path):
        for file_name in os.listdir(path):
            if file_name.endswith(".md"):
                file_path = os.path.join(path, file_name)
                run_cleanup(file_path)
    else:
        print(f"Error: {path} is not a valid file or directory.")


if __name__ == "__main__":
  main()