import os, re

from src.utils import apply_renaming_logic
from src.constants import REFS

# region Regex
# For unescaping characters
CHARACTER_REGEX = r"\\([\<\>\{\}\(\)\"\'@~&])"
SPAN_REGEX = r"(\[.+?\]\{[^\{\}]+?\})"
REF_REGEX = r"\[\\\[((?:i\.)?\d{1,2})\\\]\]\((\d{1,2}-references.md#\1)\)"

# For escaped characters inside of grid tables, preserve the positioning of the table structural elements (ex., piples) by adding a space of padding for each "unescaped" character before the column's closing pipe
REGEX_IN_TABLE = rf"\|([^|\n]*?(?:{CHARACTER_REGEX}|\\([\[\]]))[^|\n]*)\|"
# endregion


# region Helpers
def remove_html_comments(file_contents: str):
    """
    Remove HTML comments, which follow this pattern:

    `<!--{comment body}-->`
    """
    comment_regex = r"\<\!\-{2}.+?\-{2}\>"
    file_contents = re.sub(comment_regex, "", file_contents)

    return file_contents


def simplify_references_to_text(file_contents: str):
    """
    Convert bibliographic reference links to simple text format.
    
    Converts patterns like [[i.6]](clause-2.md#i.6) or [[1]](2-references.md#1)
    to simple text like [i.6] or [1] for better readability.

    Inside grid table columns the characters removed by the simplification are
    compensated by appending spaces before the closing pipe, so the fixed-width
    column structure is preserved.
    """
    # Match reference links with escaped brackets: \[\[ref\]\](link)
    ref_link_pattern = r"\[\\\[((?:i\.|n\.)?\d{1,2})\\\]\]\([^\)]+\)"

    # Also match already unescaped references: [[ref]](link)
    ref_link_pattern_unescaped = r"\[\[((?:i\.|n\.)?\d{1,2})\]\]\([^\)]+\)"

    # Pattern for a grid-table column (|…|) that contains at least one reference
    ref_in_column_pattern = (
        r"\|([^|\n]*"
        r"(?:\[\\\[(?:i\.|n\.)?\d{1,2}\\\]\]\([^\)]+\)|\[\[(?:i\.|n\.)?\d{1,2}\]\]\([^\)]+\))"
        r"[^|\n]*)\|"
    )

    def replace_ref_in_column(match: re.Match):
        column_text = match.group(1)
        length_before = len(column_text)

        column_text = re.sub(ref_link_pattern, r"[\1]", column_text)
        column_text = re.sub(ref_link_pattern_unescaped, r"[\1]", column_text)

        padding = " " * (length_before - len(column_text))
        return f"|{column_text}{padding}|"

    # Phase 1 – grid table columns: replace with padding to preserve column width
    prev_contents = None
    while file_contents != prev_contents:
        prev_contents = file_contents
        file_contents, _ = re.subn(ref_in_column_pattern, replace_ref_in_column, file_contents)

    # Phase 2 – everything else: plain replacement
    file_contents = re.sub(ref_link_pattern, r"[\1]", file_contents)
    file_contents = re.sub(ref_link_pattern_unescaped, r"[\1]", file_contents)

    return file_contents


def convert_links_to_markdown(file_contents: str):
    """Since Pandoc doesn't do it automatically, change the file extensions within links to other locations in the document from `.html` to `.md`"""
    # For links inside of grid tables, preserve the positioning of the table structural elements (ex., pipes) by "replacing" the two letters lost in the transition from "html" to "md" with spaces appended to the end of the link
    regex_in_table = (
        r"\|([^|\n]*?\(\d{1,2}-.+?)\.html#((?:i\.)?\d{1,2}|[\w.-]+?\)[^|\n]*?)\|"
    )
    replace_in_table = r"|\1.md#\2  |"

    # For all other links
    regex_not_in_table = r"\((\d{1,2}-.+?)\.html#((?:i\.)?\d{1,2}|[\w.-]+?)\)"
    replace_not_in_table = r"(\1.md#\2)"

    while True:
        file_contents, count = re.subn(regex_in_table, replace_in_table, file_contents)
        if (
            count == 0
        ):  # Break out of the loop once there aren't any more substitutions made
            break

    file_contents = re.sub(regex_not_in_table, replace_not_in_table, file_contents)
    return file_contents


def unescape_characters(file_contents: str, is_cleanup: bool):
    """
    During conversion to Markdown, Pandoc automatically escapes Markdown special characters. In some cases, this is useful, however for others, this makes reading the text more difficult with no benefit, as the characters work fine for plain text if they aren't used in a way that triggers their special functionality.

    Removes the backslash from before the following characters, thereby "unescaping" them:
    - `<` and `>`
    - `{` and `}`
    - `(` and `)`
    - `[` and `]`
    - `"` and `'`
    """

    def unescape_brackets_in_line(line: str):
        """Unescape brackets in a single line of text, returning the newly processed line and the number of brackets unescaped. This number is necessary to maintain padding inside of grid tables."""

        def unescape_brackets_in_string(escape_string: str):
            return re.sub(r"\\([\[\]])", r"\1", escape_string)

        if not ("\\[" in line or "\\]" in line):
            # Nothing to do, return the line and 0 for the number of lines escaped
            return line, 0

        replacement_line: list[str] = []
        end_of_last_match = 0

        len_before = len(line)

        for regex in [SPAN_REGEX, REF_REGEX]:
            # Do not escape brackets in references or
            for match in re.compile(regex).finditer(line):
                # Escape any brackets before the match
                text_before_match = line[end_of_last_match : match.start()]
                text_before_match = unescape_brackets_in_string(text_before_match)
                replacement_line.append(text_before_match)

                # Keep the match as it is
                replacement_line.append(match.group(0))

                # Prepare for next match
                end_of_last_match = match.end()

        # Handle the part of the line after the final match
        text_after_last_match = line[end_of_last_match:]
        text_after_last_match = unescape_brackets_in_string(text_after_last_match)
        replacement_line.append(text_after_last_match)

        new_line = "".join(replacement_line)

        # Calculate number of brackets escaped for table padding
        len_after = len(new_line)
        num_brackets_escaped = len_before - len_after

        return new_line, num_brackets_escaped

    def unescape_brackets(file_contents: str):
        """Unescape brackets `[` and `]` outside of spans, but keep them escaped inside of spans to avoid Pandoc mistaking them for the span's opening/closing tags"""
        lines = file_contents.split("\n")
        replacement_lines: list[str] = []

        for line in lines:
            if re.search(r"\|(?:[^\|]+?)\|", line):
                replacement_lines.append(line)
                continue  # This is in a table, lines in tables are handled with `replace_in_table`

            replacement_line, _ = unescape_brackets_in_line(line)
            replacement_lines.append(replacement_line)

        file_contents = "\n".join(replacement_lines)

        return file_contents

    def replace_in_table(match: re.Match):
        column_text: str = match.group(1)
        column_text = column_text.replace(
            "\xa0", " "
        )  # Replace non-breaking spaces with normal spaces
        length_before = len(column_text)

        if is_cleanup:
            # Remove trailing backslashes that get appended to the end of some [] pairs
            column_text = column_text.replace("\\[\\]\\", "[]")

        column_text = re.sub(CHARACTER_REGEX, r"\1", column_text)

        # Handle brackets
        column_text, _ = unescape_brackets_in_line(column_text)

        length_after = len(column_text)

        new_column = f'|{column_text}{" " * (length_before - length_after)}|'

        return new_column

    def unespace_captions(file_contents: str):
        """Remove extraneous spaces in figure and table captions, which are denoted by starting with `**` and ending with `**`"""
        lines = file_contents.split("\n")
        replacement_lines: list[str] = []
        
        for line in lines:
            # Check if line contains escaped asterisks and Figure/Table caption
            # Unescape \*\* to ** for caption lines
            if "\\*\\*" in line and ("Figure" in line or "Table" in line):
                # Replace all \* with * in this line
                line = line.replace("\\*", "*")
            
            # Clean up extra spaces in captions
            if "|" in line: #we need to add spaces to keep the table structure
                new_line = re.sub(r"\*\*\s*((?:Figure|Table)[^\*]*?)\s*\*\*", r"**\1**    ", line)
            else:
                new_line = re.sub(r"\*\*\s*((?:Figure|Table)[^\*]*?)\s*\*\*", r"**\1**", line)
            replacement_lines.append(new_line)
        file_contents = "\n".join(replacement_lines)
        return file_contents

    prev_contents = None
    while file_contents != prev_contents:
        prev_contents = file_contents
        file_contents, _ = re.subn(REGEX_IN_TABLE, replace_in_table, file_contents)

    # For all other escaped characters
    file_contents = re.sub(CHARACTER_REGEX, r"\1", file_contents)
    file_contents = unescape_brackets(file_contents)
    file_contents = unespace_captions(file_contents)

    return file_contents

def remove_toc_in_front_page(text: str) -> str:
    """Remove the table of contents from the front page"""
    # Find the start and end of the table of contents
    toc_start = text.find("::: TT")
    toc_end = len(text)

    # If both markers are found, remove the table of contents
    if toc_start != -1 and toc_end != -1:
        text = text[:toc_start] + text[toc_end:]

    return text

def add_ignore_prettier_text_before_after_tables(text: str) -> str:
    """Add the text `--- IGNORE ---` before and after each table in the Markdown file to prevent Prettier from reformatting the tables"""
    
    new_lines = []
    lines = text.split("\n")
    inside_table = False
    for i in range(len(lines)):
        line = lines[i]
        if line.startswith("+--") or line.startswith("+=="):
            if not inside_table:
                new_lines.append("<!-- prettier-ignore-start -->")
                inside_table = True
                new_lines.append(line)
            else:           
                new_lines.append(line)
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if not (next_line.startswith("|") or next_line.startswith("+--") or next_line.startswith("+==")):
                        inside_table = False
                        new_lines.append("<!-- prettier-ignore-end -->")
        else:
            new_lines.append(line)

    return "\n".join(new_lines)


def rename_html_classes_in_text(text: str) -> str:
    """Apply the renaming logic to all HTML classes in the text"""
    return text.replace("{.HTML_","{.HTML-")


def merge_split_class_spans_around_inline_styles(text: str) -> str:
    """
    Merge adjacent Markdown spans that share the same class when inline styles
    split the class into multiple chunks.

    Supported wrappers:
    - strong: **...**
    - emphasis/italic: *...* and _..._
    - underline: <u>...</u>

    Example:
    [a]{.HTML-Code}**[b]{.HTML-Code}**[c]{.HTML-Code}
    -> [a**b**c]{.HTML-Code}
    """

    span_text = r"(?:\\.|[^\]])*"
    class_expr = r"[^{}]+"

    wrappers = [
        ("**", "**"),
        ("*", "*"),
        ("_", "_"),
        ("<u>", "</u>"),
    ]

    while True:
        previous = text

        for open_tag, close_tag in wrappers:
            open_tag_escaped = re.escape(open_tag)
            close_tag_escaped = re.escape(close_tag)

            pattern_plain_styled_plain = re.compile(
                rf"\[(?P<left>{span_text})\]\{{(?P<class>{class_expr})\}}"
                rf"{open_tag_escaped}\[(?P<mid>{span_text})\]\{{(?P=class)\}}{close_tag_escaped}"
                rf"\[(?P<right>{span_text})\]\{{(?P=class)\}}"
            )
            pattern_plain_styled = re.compile(
                rf"\[(?P<left>{span_text})\]\{{(?P<class>{class_expr})\}}"
                rf"{open_tag_escaped}\[(?P<mid>{span_text})\]\{{(?P=class)\}}{close_tag_escaped}"
            )
            pattern_styled_plain = re.compile(
                rf"{open_tag_escaped}\[(?P<mid>{span_text})\]\{{(?P<class>{class_expr})\}}{close_tag_escaped}"
                rf"\[(?P<right>{span_text})\]\{{(?P=class)\}}"
            )

            text = pattern_plain_styled_plain.sub(
                lambda m: (
                    f"[{m.group('left')}{open_tag}{m.group('mid')}{close_tag}{m.group('right')}]"
                    f"{{{m.group('class')}}}"
                ),
                text,
            )
            text = pattern_plain_styled.sub(
                lambda m: (
                    f"[{m.group('left')}{open_tag}{m.group('mid')}{close_tag}]"
                    f"{{{m.group('class')}}}"
                ),
                text,
            )
            text = pattern_styled_plain.sub(
                lambda m: (
                    f"[{open_tag}{m.group('mid')}{close_tag}{m.group('right')}]"
                    f"{{{m.group('class')}}}"
                ),
                text,
            )

        if text == previous:
            break

    return text

# region Import from Word Logic
def remove_leading_tab(filename: str) -> str:
    REF_REGEX = r"(\d+)-tab"
    filename = re.sub(REF_REGEX, r"\1-", filename)
    return filename

def remove_autonumbered_content(text: str) -> str:
    """
    Remove content that was automatically numbered by the toolchain and is not present in the original markdown. This includes:
    - Auto-numbered table captions (e.g., "Table 1.2.3-1:~~~ Description of the table" → "Table: Description of the table")
    - Auto-numbered table captions (e.g., "Table A.2.3-1:~~~ Description of the table" → "Table: Description of the table")
    - Auto-numbered figure captions (e.g., "Figure 1.2.3-1:~~~ Description of the figure" → "Figure: Description of the figure")
    - Auto-numbered figure captions (e.g., "Figure B.2.3-1:~~~ Description of the figure" → "Figure: Description of the figure")
    - Auto-numbered example captions (e.g., ">>> [!tip] EXAMPLE 1:~~~" → ">>> [!tip]")
    - Auto-numbered note captions (e.g., ">>> [!note] NOTE:~~~" → ">>> [!note]")
    """

    # Normalize numbered Table/Figure captions that are system-generated
    # and always end with the exact sequence ':~~~'. Examples:
    # **Figure 1.2.3.4-1:~~~ Caption**  -> **Figure: Caption**
    # **Table A.1.2.3-1:~~~ Caption**   -> **Table: Caption**
    text = re.sub(
        r"\*\*(Table|Figure) ([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*)[-‑–]\d+:~~~ (.*?)\s*\*\*",
        r"**\1: \3**",
        text,
    )

    # Handle notes inside grid-table cells: replace the auto-numbered label
    # (e.g. "| >>> [!note] NOTE 1:~~~") with spaces of equal length so the
    # table column width is preserved.
    def _replace_table_note_with_spaces(match: re.Match):
        prefix = match.group(1)
        removed = match.group(2)
        return f"{prefix}{' ' * len(removed)}"

    text = re.sub(
        r"(\| >>> \[!note\] )(NOTE(?: \d+)?:~~~)",
        _replace_table_note_with_spaces,
        text,
        flags=re.IGNORECASE,
    )

    # Normalize callout labels (non-table) where the system emitted a label
    # followed by an optional number and the exact ':~~~' suffix.
    # Examples:
    # >>> [!tip] EXAMPLE:~~~       -> >>> [!tip]
    # >>> [!note] NOTE 1:~~~       -> >>> [!note]
    def _callout_repl(m: re.Match):
        typ = m.group('t').lower()
        return f">>> [!{typ}] "

    text = re.sub(
        r"^(>>> \[!(?P<t>tip|note)\] )(?:EXAMPLE|NOTE)(?: \d+)?:~~~",
        _callout_repl,
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # Also handle the rare case where the callout contains only the tildes
    # (e.g. >>> [!note] ~~~) by removing the tildes as well.
    text = re.sub(
        r"^(>>> \[!(?P<t2>tip|note)\] )~~~",
        lambda m: f">>> [!{m.group('t2').lower()}] ",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    return text


# endregion


def postprocess(markdown_dir: str, is_cleanup: bool):
    """
    ### Description
    Iterates through the generated Markdown files, applying various transformations to improve 
    formatting and readability:
    
    1. Removes table of contents from front page
    2. Removes HTML comments from all files
    3. Converts links from HTML to Markdown format
    4. Unescapes special characters that Pandoc unnecessarily escaped:
       - Angle brackets, curly braces, parentheses, quotes
       - Square brackets with special handling for tables and spans
    5. Adds prettier-ignore comments before and after tables to preserve formatting
    6. Renames HTML classes to use hyphens instead of underscores
    7. Applies special handling for reference pages
    
    ### Args
    - `markdown_dir`: String path to directory containing the generated Markdown files
    - `is_cleanup`: `True` if additional formatting should be performed (when converting from "dirty" HTML), `False` otherwise
    """

    for filename in os.listdir(markdown_dir):
        if filename.endswith(".md"):
            file_path = os.path.join(markdown_dir, filename)

            with open(file_path, "r", encoding="utf-8") as file:
                text = file.read()

            if filename == "front-page.md":
                text = remove_toc_in_front_page(text)

            text = remove_html_comments(text)

            text = convert_links_to_markdown(text)
            text = simplify_references_to_text(text)  # Convert [[i.6]](link) to [i.6]
            text = unescape_characters(text, is_cleanup)

            # text = add_ignore_prettier_text_before_after_tables(text)

            # Fix code fence language tag: ``` json → ```json (no space)
            text = re.sub(r"^(```)\s+(json|text)$", r"\1\2", text, flags=re.MULTILINE)

            # Remove empty first line inside JSON code blocks (``` json\n\n → ```json\n)
            text = re.sub(r"^(```json|text)\n\n", r"\1\n", text, flags=re.MULTILINE)

            text = text.replace("{{{{SPACE}}}}", " ")

            # Convert :::: EX/NO/TAN div blocks to >>> [!tip/!note] blockquote style
            def _convert_div_block(m):
                div_type = m.group(1)
                label = m.group(2)
                content = m.group(3)
                alert = "[!tip]" if div_type == "EX" else "[!note]"
                return f">>> {alert} {label}\n{content}\n>>>\n"

            text = re.sub(
                r"^:::: (EX|NO|TAN)\n::: \{\}\n(.*?)\n:::\n(.*?)^::::\n",
                _convert_div_block,
                text,
                flags=re.MULTILINE | re.DOTALL,
            )

            text = rename_html_classes_in_text(text)
            text = merge_split_class_spans_around_inline_styles(text)
            text = remove_autonumbered_content(text)

            if filename.replace(".md", "") in REFS:
                text = text.replace("{#list-of-references .EX}", "REFS")

            with open(file_path, "w", encoding="utf-8") as file:
                file.write(text)
