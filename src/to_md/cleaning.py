import re, json, os
from bs4 import BeautifulSoup, Tag, NavigableString, Comment

from src.utils import get_bold_italic_underline_css_classes, get_css_classes, is_whitespace_navstr

from src.constants import (
    LIST_HIERARCHY_CLASSES,
    ORDERED_LIST_ITEM_CLASSES,
    HTML_LIST_TAGS,
)

BOLD_CLASSES, ITALIC_CLASSES, UNDERLINE_CLASSES = get_bold_italic_underline_css_classes("ETSIstyles.css")
CSS_CLASSES = get_css_classes("all", ["ETSIstyles.css"])


# region Helpers
def ensure_correct_css_class_use(soup: BeautifulSoup):
    """Reassigns the ondemand classes applied by some divs and spans to established alternatives. Unwraps other divs and spans that needlessly apply classes."""

    def handle_tags_to_unwrap(soup: BeautifulSoup):
        """
        Handles the following classes:
        - `ondemand_CHAR_color_000000`
        - `ondemand_PAR_space_after_3`
        - `ondemand_PAR_space_after_6`
        - `ondemand_PAR_space_after_10`
        - `ondemand_PAR_alignment_CENTER_space_before_3`
        - `ondemand_CHAR_name_Century_Gothic_size_16_color_FFFFFF`
        - `ondemand_CHAR_size_9`
        - `ondemand_CHAR_name_Arial_size_9`
        - `ondemand_CHAR_size_9_color_000000`
        - `ondemand_CHAR_size_12_color_000000`
        - `example-title`
        """
        CLASSES_TO_UNWRAP: list[str] = [
            "ondemand_CHAR_color_000000",
            "ondemand_PAR_space_after_3",
            "ondemand_PAR_space_after_6",
            "ondemand_PAR_space_after_10",
            "ondemand_PAR_space_after_12",
            "ondemand_PAR_left_indent_36_space_after_10",
            "ondemand_PAR_alignment_CENTER_space_before_3",
            "ondemand_CHAR_name_Century_Gothic_size_16_color_FFFFFF",
            "ondemand_CHAR_size_9",
            "ondemand_CHAR_name_Arial_size_9",
            "ondemand_CHAR_size_9_color_000000",
            "ondemand_CHAR_size_12_color_000000",
            "example-title",
            "block"
        ]

        divs_to_unwrap = soup.find_all(
            lambda tag: tag.has_attr("class")
            and any(cls in CLASSES_TO_UNWRAP for cls in tag["class"])
        )

        for div in divs_to_unwrap:
            div.unwrap()

        return soup

    def handle_tags_to_reassign(soup: BeautifulSoup):
        """
        Makes the following switches:
        - `ondemand_CHAR_color_0000FF` -> `Hyperlink`
        - {`ondemand_CHAR_color_595959`,
          `ondemand_CHAR_name_Times_New_Roman_size_10_color_595959`} -> `HTML_Keyboard`
        - `ondemand_PAR_alignment_CENTER_space_after_12` -> `FL`
        - `ondemand_CHAR_name_Roboto_Mono_size_8_color_31849B` -> `HTML_Code`
        - `ondemand_PAR_alignment_CENTER` -> `TAC`
        - {`ondemand_CHAR_name_Courier_New`,
          `ondemand_CHAR_name_Courier_New_size_9`,
          `ondemand_CHAR_name_Courier_New_size_8`} -> `PL`
        """
        class_pairs = [  # Format [<class to replace>, <replacement class>]
            ["ondemand_CHAR_color_0000FF", "Hyperlink"],
            ["ondemand_CHAR_color_595959", "HTML_Keyboard"],
            ["ondemand_PAR_alignment_CENTER_space_after_12", "FL"],
            ["ondemand_CHAR_name_Roboto_Mono_size_8_color_31849B", "HTML_Code"],
            ["ondemand_PAR_alignment_CENTER", "TAC"],
            ["ondemand_CHAR_name_Courier_New", "PL"],
            ["ondemand_CHAR_name_Courier_New_size_8", "PL"],
            ["ondemand_CHAR_name_Courier_New_size_9", "PL"],
            [
                "ondemand_CHAR_name_Times_New_Roman_size_10_color_595959",
                "HTML_Keyboard",
            ],
            [
                "ETSI-code_Char",
                "HTML_Sample"
            ],
        ]

        for i in range(len(class_pairs)):
            tags: list[Tag] = soup.find_all(class_=class_pairs[i][0])
            for tag in tags:
                tag["class"] = [class_pairs[i][1]]

        return soup

    def correct_span_styles(soup: BeautifulSoup):
        """Some styles corresponding to Word paragraph styles, and therefore should only be applied to `<div>`s and `<p>`s, are also applied to spans, which should only use styles that correspond to Word run styles. In such cases, make the necessary substitutions."""
        STYLES_AND_REPLACEMENTS = [["PL", "HTML_Sample"]]

        for pair in STYLES_AND_REPLACEMENTS:
            before_style = pair[0]
            after_style = pair[1]

            spans = soup.find_all("span", class_=before_style, recursive=True)
            for span in spans:
                span["class"] = [after_style]

        return soup

    def handle_exceptional_cases(soup: BeautifulSoup):
        """
        Some CSS classes need very specific handling. This handling is done here.

        Classes impacted:
        - "ondemand_PAR_first_line_indent_56"
        - "ondemand_PAR_first_line_indent_70"
        """

        def handle_ondemand_PAR_first_line_indent_56_and_70(
            soup: BeautifulSoup,
        ):
            """Maintaining the span inside these divs, replace the div that wraps it with a paragraph. These classes appear only in code block sequences, so form the format expected during code block creation here."""
            CLASSES = [
                "ondemand_PAR_first_line_indent_56",
                "ondemand_PAR_first_line_indent_70",
            ]
            divs = (
                soup.find("html")
                .find("body")
                .find_all(
                    "div",
                    attrs={"class": lambda c: c and any(cls in c for cls in CLASSES)},
                    recursive=False,
                )
            )

            for div in divs:
                spans = div.find_all("span")
                span_cls = spans[0].get("class")[
                    0
                ]  # All the classes should be the same here

                # Consolidated the contents of all the spans into a new span
                span_contents = "".join([s.get_text() for s in spans])
                consolidated_span = soup.new_tag("span", attrs={"class": span_cls})
                consolidated_span.append(NavigableString(span_contents))

                # Cate a new paragraph for the consolidated span and insert it after the div
                paragraph = soup.new_tag("p")
                paragraph.append(consolidated_span)
                div.insert_after(paragraph)

                # Remove the div
                div.decompose()

            return soup

        soup = handle_ondemand_PAR_first_line_indent_56_and_70(soup)

        return soup

    soup = handle_tags_to_unwrap(soup)
    soup = handle_tags_to_reassign(soup)
    soup = handle_exceptional_cases(soup)
    soup = correct_span_styles(soup)

    return soup


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
            if text[i] == '"' and (i == 0 or text[i-1] != '\\'):
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
    cleaned = re.sub(r'(?<!:)(?<=[\[\{\,\s])//[^\n]*|^//[^\n]*', replace_comment, cleaned, flags=re.MULTILINE)
    
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
    non_conform_pattern = r'(?:^|\s)((?:\.{3,}|…)(?:\s*etc\.?)?|etc\.)(?=\s|,|$)'
    cleaned = re.sub(non_conform_pattern, lambda m: m.group(0)[:m.start(1)-m.start(0)] + replace_nonconform(m) if not is_in_string(m.start(1), string_ranges) else m.group(0), cleaned, flags=re.MULTILINE)
    
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
            inner = [line[2:] if line.startswith("  ") else line for line in lines_fmt[1:-1]]
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


def convert_source_code_divs(soup: BeautifulSoup):
    """
    Convert <div class="Source_Code"> (and EX divs that directly contain only HTML-Sample
    spans) into proper <div class="sourceCode"><pre><code class="language-json"> blocks,
    preserving all whitespace.

    In the html_dirty produced from a DOCX, code blocks appear as one or more consecutive
    divs with class "Source_Code" whose children are <span class="HTML-Sample"> elements.
    Spans that contain a <br /> mark a line break; all other spans contribute their text.
    Spaces may have been encoded as non-breaking spaces (\xa0) to survive Pandoc — these
    are converted back to regular spaces.

    Consecutive sibling Source_Code divs are merged into a single block so that code
    blocks that were split across Word paragraphs are reunited.
    """

    HTML_SAMPLE_CLASSES = {"HTML-Sample", "HTML_Sample"}

    def extract_text(div: Tag) -> str:
        """Return the plain text of a Source_Code / EX content div, honouring <br /> as newlines."""
        parts = []
        for child in div.children:
            if isinstance(child, NavigableString):
                text = str(child).replace("\xa0", " ")
                # Skip vanish-run markers inserted during DOCX round-trip
                if text.strip() and text.strip() not in ("jsonStartBlockquote", "jsonEndBlockquote"):
                    parts.append(text)
                continue
            if not isinstance(child, Tag) or child.name != "span":
                continue
            if not HTML_SAMPLE_CLASSES.intersection(child.get("class", [])):
                continue
            if child.find("br"):
                parts.append("\n")
            else:
                # Replace newlines and non-breaking spaces with regular spaces
                parts.append(child.get_text().replace("\xa0", " ").replace("\n", " "))
        return "".join(parts)

    def has_only_html_sample_content(div: Tag) -> bool:
        """Return True iff every non-whitespace child of *div* is an HTML-Sample span."""
        found_sample = False
        for child in div.children:
            if isinstance(child, NavigableString):
                if child.strip():
                    return False  # bare text outside a span → not pure code
                continue
            if not isinstance(child, Tag):
                continue
            if child.name == "span" and HTML_SAMPLE_CLASSES.intersection(child.get("class", [])):
                found_sample = True
            else:
                return False  # non-HTML-Sample element present
        return found_sample

    def make_block(text: str) -> Tag:
        text = text.strip("\n") + "\n"
        source_div = soup.new_tag("div", attrs={"class": "sourceCode"})
        pre = soup.new_tag("pre")
        code = soup.new_tag("code", attrs={"class": "language-json"})
        code.append(NavigableString(text))
        pre.append(code)
        source_div.append(pre)
        return source_div

    processed: set[int] = set()

    for div in list(soup.find_all("div", class_="Source_Code")):
        if id(div) in processed:
            continue

        # Collect this div and any immediately following Source_Code siblings
        group = [div]
        sibling = div.next_sibling
        while sibling is not None:
            if isinstance(sibling, NavigableString) and not sibling.strip():
                sibling = sibling.next_sibling
                continue
            if isinstance(sibling, Tag) and "Source_Code" in sibling.get("class", []):
                group.append(sibling)
                sibling = sibling.next_sibling
            else:
                break

        combined = "".join(
            (extract_text(sd) + ("\n" if not extract_text(sd).endswith("\n") else ""))
            for sd in group
        )
        combined = try_reformat_json(combined)

        block = make_block(combined)
        group[0].insert_before(block)
        for sd in group:
            processed.add(id(sd))
            sd.decompose()

    # Handle EX (and NO) divs whose content div is exclusively HTML-Sample spans.
    # Structure expected:
    #   <div class="EX">
    #     <div>EXAMPLE N:</div>          ← title, classless
    #     <div><span class="HTML-Sample">...</span> ...</div>  ← content, classless
    #   </div>
    # The content div is replaced by a proper <div class="sourceCode"> block so that
    # Pandoc reads it as a CodeBlock, which format_example_or_note() handles correctly.
    for ex_div in list(soup.find_all("div", class_=["EX", "NO"])):
        child_divs = [
            child for child in ex_div.children
            if isinstance(child, Tag) and child.name == "div" and not child.get("class")
        ]
        if len(child_divs) != 2:
            continue
        content_div = child_divs[1]
        if not has_only_html_sample_content(content_div):
            continue
        text = extract_text(content_div)
        if not text.strip():
            continue
        text = try_reformat_json(text)
        content_div.replace_with(make_block(text))

    return soup

def handle_blockquotes(soup: BeautifulSoup):
    """Unwrap blockquotes, preserving their contents"""

    for blockquote in soup.find_all("blockquote"):
        blockquote.unwrap()

    return soup


def remove_redundant_parent_tags_when_children_have_classes(soup: BeautifulSoup):
    """
        Some children can have classes that imposes specific text styles such as 'bold' or 'italic'. They might be wrapped in parents such as strong and em tags that are redendant.
        We need to unwrap them to avoid adding unecessary markdown syntax in the final markdown output.
    """
    CLASSES = CSS_CLASSES
    # For all elements that have one of the classes in CLASSES, if their parent is a strong or em tag, unwrap the parent
    for cls in CLASSES:
        tags_to_unwrap = []
        if cls in BOLD_CLASSES:
            tags_to_unwrap.extend(["strong", "b"])
        if cls in ITALIC_CLASSES:
            tags_to_unwrap.extend(["em", "i"])
        if cls in UNDERLINE_CLASSES:
            tags_to_unwrap.extend(["u"])

        if not tags_to_unwrap:
            continue

        elements = soup.find_all(class_=cls)
        for element in elements:
            parent = element.parent
            while(parent and parent.name in tags_to_unwrap):
                parent.unwrap()
                parent = element.parent

    return soup


def remove_example_tag_number_from_body(soup: BeautifulSoup):
    """Some examples have their number mistakenly copied and added as part of their body. Remove those from the body."""
    divs: list[Tag] = soup.find_all("div", class_="EX")
    regex = r"(?:EXAMPLE |^\s*)?((?:(?:[0-9])|(?:[1-3][0-9])))"  # Captures the number part and the ending colon, ex., 1:, 3:, 14:, etc

    for div in divs:
        children = [
            child
            for child in div.children
            if (isinstance(child, Tag) and (child.name == "div"))
        ]

        if len(children) != 2:
            continue  # Skip this one because the problem only occurs in examples with exactly two children

        # Getting the children and matches in their text
        tag = children[0]
        tag_text = tag.get_text(strip=True)
        tag_match = re.search(regex, tag_text)

        body = children[1]
        body_text = body.get_text(strip=True)
        body_match = re.search(regex, body_text)

        # Disqualify divs
        if not (body_match and tag_match) and not body_match == tag_match:
            continue  # The example number isn't repeated in the body here

        if not (isinstance(tag, Tag) and isinstance(body, Tag)):
            continue  # Not two divs

        # Remove only if it's just the number/colon pair in the div and nothing else
        if len(body_text) == 2 or len(body_text) == 3:
            body.decompose()

    return soup


def handle_tags_for_empty_classes(soup: BeautifulSoup, css_src: list[str]):
    """
    Replace the tags for only those HTML tags that only have a class attribute that applies an empty CSS class with a paragraph (to maintain visual positioning).

    Ex: <div class="Empty_CSS">Content</div> -> {line beginning}Content{newline}
    """
    empty_css_classes = get_css_classes("empty", css_src)

    for tag in soup.find_all(True):
        if list(tag.attrs.keys()) == ["class"]:
            classes = tag.get("class", [])
            if len(classes) == 1 and classes[0] in empty_css_classes:
                paragraph = soup.new_tag("p")

                while tag.contents:
                    paragraph.append(tag.contents[0].extract())

                tag.replace_with(
                    paragraph
                )  # Maintain spacing between text by enclosing it in a paragraph

    return soup


def consolidate_sequential_spans(soup: BeautifulSoup, css_src: list[str]):
    """Consolidates only those series of spans that contain data that should be contained within a single span"""
    CLASSES = get_css_classes("all", css_src)

    def handle_spans(soup: BeautifulSoup, tag: Tag):
        nonlocal CLASSES
        children = list(tag.children)
        i = 0

        while i < len(children):
            child = children[i]

            if isinstance(child, Tag) and child.name == "span":
                span_class = child.get("class", [])

                if len(span_class) == 1 and span_class[0] in CLASSES:
                    span_class = span_class[0]
                    group = [child]
                    i += 1

                    # Get consecutive spans, possibly separated by whitespace
                    while i < len(children):
                        next_child = children[i]

                        if (  # Spans
                            isinstance(next_child, Tag)
                            and next_child.name == "span"
                            and next_child.get("class", []) == [span_class]
                        ):
                            group.append(next_child)
                            i += 1
                        elif is_whitespace_navstr(next_child):
                            i += 1
                        else:  # End of sequence
                            break

                    # Create new consolidated span
                    if len(group) > 1:
                        new_parent_span = soup.new_tag("span", **{"class": span_class})

                        for span in group:
                            for contents in list(span.contents):
                                new_parent_span.append(contents.extract())

                        group[0].insert_before(new_parent_span)

                        # Remove old spans
                        for span in group:
                            span.decompose()

                        children = list(tag.children)
                        i = children.index(new_parent_span) + 1

                else:
                    i += 1

            else:
                i += 1

        return soup

    def handle_spans_not_in_tables(soup: BeautifulSoup):
        divs = soup.find_all("div")

        paras = soup.find_all("p")

        for div in divs:
            soup = handle_spans(soup, div)

        for para in paras:
            soup = handle_spans(soup, para)

        return soup

    def handle_spans_in_tables(soup: BeautifulSoup):
        tables = soup.find_all("table")

        for table in tables:
            cells = table.find_all(["td", "th"])

            for cell in cells:
                soup = handle_spans(soup, cell)

                divs = cell.find_all("div")

                for div in divs:
                    soup = handle_spans(soup, div)

        return soup

    soup = handle_spans_not_in_tables(soup)
    soup = handle_spans_in_tables(soup)

    return soup


def consolidate_div_sequences(soup: BeautifulSoup):
    """
    Consolidates sequences of divs that apply the following classes to their contents:
    - `PL`
    - `EX`
    - `NO`
    - `EW`

    Divs applying these classes are meant to go together
    """
    EXAMPLES_NOTES_CLASSES = ["EX", "NO"]

    CLASSES = EXAMPLES_NOTES_CLASSES + ["B1plus", "PL", "EW"]

    def is_beginning_ex_no(div: Tag):
        """
        Checks example and note divs to see if they should be the start of an example or note - that is, who have two classless child divs and no other HTML tags

        Returns `True` for such divs, `False` for other examples or notes
        """
        nonlocal EXAMPLES_NOTES_CLASSES

        if not div or not isinstance(div, Tag):
            return False

        div_class = div.get("class", [])

        if len(div_class) != 1 or div["class"][0] not in EXAMPLES_NOTES_CLASSES:
            return False

        # Children of parent div
        children = [
            child
            for child in div.contents
            if isinstance(child, Tag)
            or (isinstance(child, NavigableString) and not child.strip() == "")
        ]

        # All children that are classless divs
        div_children = [
            child
            for child in children
            if isinstance(child, Tag)
            and child.name == "div"
            and len(child.get("class", [])) == 0
        ]

        # Does this div have only two child divs?
        is_top_level_div: bool = len(div_children) == 2 and len(children) == len(
            div_children
        )

        return is_top_level_div

    def div_is_in_series(current: Tag, next: Tag):
        """
        ### Description
        Determine whether a div is in a series by checking the next tag

        ### Arguments
        - `current`: The div being tested
        - `next`: The div after `current` within a list of all divs in the soup
        """
        if not current.name == "div" and not next.name == "div":
            return False

        current_class = current.get("class")
        current_class = current_class[0] if current_class else None

        next_class = next.get("class")
        next_class = next_class[0] if next_class else None

        if (
            not current_class
            or not next_class
            or (current_class != next_class)
            or is_beginning_ex_no(next)
        ):
            return False

        current_sibling = current.find_next_sibling(lambda tag: isinstance(tag, Tag))

        if next is not current_sibling:
            return False

        return True

    def populate_group(group: list[Tag], divs: list[Tag]):
        """Gets the divs that follow. Populates `group` with the elements that should be part of a previous example or note's body."""
        nonlocal div_class, i  # `i` is the index used with the while loop

        while i < len(divs) and div_is_in_series(group[-1], divs[i]):
            group.append(divs[i])
            i += 1

        return group

    def add_body_div(soup: BeautifulSoup, group: list[Tag]):
        """Wrap all the divs' content within a single div in the example or note. Add this new div to the example/note and remove the old divs that are in `group`."""
        nonlocal div_class

        PARENT = group[0].parent
        POSITION = group[-1].next_sibling
        FIRST_DIV_ID = group[0].get("id", "")
        IS_REFERENCE = FIRST_DIV_ID.startswith("n.") or FIRST_DIV_ID.startswith("i.")

        def move_old_elements_to_div(new_parent_div: Tag):
            nonlocal PARENT, POSITION, soup, group
            for child in group:
                # Append the contents of each child div to a paragraph
                paragraph = soup.new_tag("p")
                is_list: bool = False
                for contents in list(child.contents):
                    paragraph.append(contents.extract())

                # Append the paragraph to the parent
                if not is_list:
                    new_parent_div.append(paragraph)

                # Remove the child
                child.decompose()

            return new_parent_div

        # Create new parent div
        new_parent_div = soup.new_tag(
            "div",
            **{
                "class": div_class,
                "id": "list-of-references" if IS_REFERENCE else None,
            },
        )
        new_parent_div = move_old_elements_to_div(new_parent_div)

        # Add new parent div back to the HTML
        if POSITION and isinstance(POSITION, (Tag, NavigableString)):
            POSITION.insert_before(new_parent_div)
        else:
            PARENT.append(new_parent_div)

        return soup

    def prep_examples(soup: BeautifulSoup):
        """Some example body elements may have irregular formats. Normalize them to allow the function to correctly consolidate them."""

        def fix_html_sample_and_html_code_discrepancies(soup: BeautifulSoup):
            """
            Handles example body elements that take the following form:

            ```
            <div class="EX">
              <span class="HTML_Sample">[indentation]</span><span class="HTML_Code">[body component]</span>
            </div>
            ```

            Unwraps the inner div to produce the following normalized form:

            ```
            <div class="EX">
              <span class="HTML_Code">[indentation][body component]</span>
            </div>
            ```
            """
            examples = soup.find_all("div", attrs={"class": "EX"})

            for example in examples:
                children = example.find_all(recursive=False)

                if len(children) != 2:
                    continue

                if children[0].name != "span" or children[1].name != "span":
                    continue

                if re.search(r"\[(?:i\.)?\d{1,2}\]", children[0].get_text().strip()):
                    continue  # This is a reference, not an example

                indentation_tag = children[0]
                body_tag = children[1]
                body_classes = body_tag.get("class") or []
                if not body_classes:
                    continue
                cls = body_classes[0]

                new_tag_text = f"{indentation_tag.get_text()}{body_tag.get_text()}"
                new_tag = soup.new_tag("span", attrs={"class": cls})
                new_tag.append(new_tag_text)

                indentation_tag.insert_after(new_tag)
                indentation_tag.decompose()
                body_tag.decompose()

            return soup

        soup = fix_html_sample_and_html_code_discrepancies(soup)

        return soup

    soup = prep_examples(soup)

    divs = soup.find_all("div")
    i = 0

    while i < len(divs) - 1:
        div = divs[i]
        div_class = div.get("class", [])

        # Operate only on divs with one class which is in `classes`...
        if (
            len(div_class) == 1
            and div_class[0] in CLASSES
            and div.parent.name
            != "li"  # Causes problems with divs inside of list items
        ):
            # Skip divs with only one child in them...
            if div_class[0] in EXAMPLES_NOTES_CLASSES and is_beginning_ex_no(div):
                i += 1
                continue

            if not div_is_in_series(div, divs[i + 1]):
                i += 1
                continue

            # ...Otherwise, continue on
            div_class = div_class[0]
            group = [div]  # Start tracking the divs, adding this first div
            i += 1

            group = populate_group(group, divs)

            if len(group) < 2:
                continue  # There is nothing left to do

            soup = add_body_div(soup, group)

        else:
            i += 1

    return soup


def format_lists(soup: BeautifulSoup):
    """
    ### Description
    From sequences of divs applying list styles to single list items, form nested list structures.

    ### Process
    1. Unwraps the divs that apply the list class to individual elements and applies that class to the list itself.
    2. Make lists out of list items contained in divs.
    3. Nest sublists within lists where appropriate.
    """

    def unwrap_list_items(soup: BeautifulSoup):
        """Unwrap the divs applying the class name and add the class to the top-level `<ul>` or `<ol>`."""

        def unwrap_list_items(ol_ul: Tag):
            """Unwrap the contents of individual list items, but if the list item has multiple elements inside, convert those divs to paragraphs and wrap them inside a single parent paragraph."""
            for li in ol_ul.find_all("li", recursive=False):
                # Only find direct children divs, not those in nested lists
                divs: list[Tag] = li.find_all("div", recursive=False)

                if not divs:
                    continue

                # Check if this li has nested lists as direct children
                has_nested_lists = any(
                    child.name in HTML_LIST_TAGS 
                    for child in li.children 
                    if isinstance(child, Tag)
                )

                div = divs[0]
                list_class = div.get("class")
                if not ol_ul.get("class") and list_class:
                    ol_ul["class"] = list_class

                # If there's only one div and no nested lists, simply unwrap it
                if len(divs) == 1 and not has_nested_lists:
                    div.unwrap()
                    continue
                
                # If there's only one div but there ARE nested lists, still unwrap it
                # The nested lists should remain untouched
                if len(divs) == 1 and has_nested_lists:
                    div.unwrap()
                    continue

                # If it has more than one div (and no nested lists mixed in),
                # wrap their contents in a single div
                new_parent_div = soup.new_tag("div", attrs={"class": "list-item"})
                for div in divs:
                    para = soup.new_tag("p")

                    for content in div.contents[:]:
                        para.append(content.extract())

                    new_parent_div.append(para)
                    div.decompose()

                li.append(new_parent_div)

            return ol_ul

        for ol_ul in soup.find_all(HTML_LIST_TAGS):

            ol_ul = unwrap_list_items(ol_ul)

        return soup

    def make_lists_from_divs(soup: BeautifulSoup):
        """Make lists out of sequences of divs that represent lists. Apply attributes when apppropriate."""

        def add_elements_to_group(group: list[Tag], i: int):
            """Iterate through `elements`, adding items to `group` while there is still a sequence of divs applying list hierarchy classes. Return `group` when finished."""
            nonlocal elements, current_class

            j = i + 1

            while j < len(elements):
                next = elements[j]
                next_class = next.get("class")
                next_class = next_class[0] if next_class else None

                if not (
                    isinstance(next, Tag)
                    and next.name == "div"
                    and next_class == current_class
                ) or (isinstance(next, Tag) and next.find(HTML_LIST_TAGS)):
                    break  # End of sequence

                group.append(next.extract())
                j += 1

            return j - 1, group

        def make_list(group: list[Tag]):
            """Return a new list from the divs contained in `group`"""

            def init_list():
                """Initialize a new ordered or unordered list based on the first element in `group`. Return an ordered list if the first element contains some kind of indexing marker (ex., *1)*, *1.*, *a.*, or *a)* ), otherwise return an unordered list."""
                nonlocal first_element_text, cls

                # Get the starting value, if it exists
                start = first_element_text.strip().split(" ")[0]
                item_match = re.search(r"^([A-Za-z0-9]+)[\.\)]\s+", start)

                # If the starting value exists, the list will be an ordered list
                if item_match:
                    item_number = item_match.group(1)

                    # Reduce any instances of <number><letter> to just <letter>
                    check = re.search(r"^\d+([A-Za-z]+)$", item_number)
                    item_number = check.group(1) if check else item_number

                    list_type = "1" if item_number.isdigit() else "a"

                    new_list = soup.new_tag(
                        "ol",
                        attrs={"class": cls, "start": item_number, "type": list_type},
                    )

                # Otherwise, it will be an unordered list
                else:
                    new_list = soup.new_tag("ul", attrs={"class": cls})

                return new_list

            first_element_text = group[0].get_text()
            cls = group[0].get("class")[0] if group[0].get("class") else None

            new_list = init_list()

            # Add group elements to the list as list items
            for elem in group:
                li = soup.new_tag("li")
                is_first_text = True
                # Iterate over a copy to avoid modifying the list while iterating
                for elem_child in elem.contents[:]:
                    if isinstance(elem_child, NavigableString):
                        text = str(elem_child)

                        # Remove bullet/numbering only from the first text element
                        if is_first_text:
                            # Strip leading whitespace for the first element
                            text = text.lstrip()

                            bullet_portion = re.search(r"^(\-\s+)", text)
                            index_portion = re.search(r"^([A-Za-z0-9]+[\.\)]\s+)", text)

                            if bullet_portion:
                                text = text[len(bullet_portion.group(0)) :]
                            elif index_portion:
                                text = text[len(index_portion.group(0)) :]

                            is_first_text = False

                        # Only append non-empty strings (but preserve whitespace)
                        if text:
                            li.append(NavigableString(text))

                    elif isinstance(elem_child, Tag):
                        # Extract and preserve HTML structure including spans
                        li.append(elem_child.extract())
                        is_first_text = False

                new_list.append(li)

            return new_list

        elements = soup.find("body").find_all(recursive=False)

        i = 0

        while i < len(elements):
            current = elements[i]
            current_class = current.get("class")
            current_class = current_class[0] if current_class else None

            is_part_of_code_block = (
                isinstance(current, Tag)
                and len(current.find_all()) == 1
                and current.find("span", attrs={"class": "HTML_Sample"})
            )

            if (
                not (isinstance(current, Tag) and current.name == "div")
                or current_class not in LIST_HIERARCHY_CLASSES
                or (is_part_of_code_block and current_class == "B1plus")
            ):
                i += 1
                continue  # Not a list item contained in a div

            # Unwrap any divs contained herein that apply the same class that `current_class` applies
            for div in current.find_all("div", attrs={"class": [current_class]}):
                div.unwrap()

            i, group = add_elements_to_group([current], i)

            new_list = make_list(group)

            current.replace_with(new_list)

            i += 1

        return soup

    def nest_lists(soup: BeautifulSoup):
        """Ensure list items are properly nested by comparing the level in the hierarchy contained in their classnames."""

        def is_list(element):
            """Returns `True` if the provided element is an ordered or unordered list, otherwise returns `False`."""
            return isinstance(element, Tag) and element.name in HTML_LIST_TAGS
        
        def is_valid_list_class(classname: str):
            """Check if the class is a valid list hierarchy class."""
            return classname in LIST_HIERARCHY_CLASSES or classname in ORDERED_LIST_ITEM_CLASSES

        def get_level(classname: str):
            """Takes a list-related classname like `B1`, `B2plus`, etc. Return an int representing the level at which the list should be nested based on the classname, ranging from 1 (top-level) to 5 (most nested). The `BN` and `BL` classes are at the top level."""
            nesting_level = (
                1 if classname in ORDERED_LIST_ITEM_CLASSES else int(classname[1])
            )
            return nesting_level

        elements = soup.find("body").find_all(recursive=False)

        for e in elements:
            if (
                isinstance(e, Tag)
                and e.name == "div"
                and e.get("class")[0] in ["B4", "B5"]
            ):
                print(f"{e}\n")

        i = 0

        while i < len(elements) - 1:
            current = elements[i]
            next = elements[i + 1]

            if not (is_list(current) and is_list(next)):
                i += 1
                continue

            # Check if elements have class attribute
            current_class_attr = current.get("class")
            next_class_attr = next.get("class")
            
            # Skip if either element has no class
            if current_class_attr is None:
                i += 1
                continue
                
            if next_class_attr is None:
                i += 1
                continue

            current_class = current_class_attr[0]
            next_class = next_class_attr[0]
            
            # Skip if either class is not a valid list class (e.g., EX, NO, TAN)
            if not is_valid_list_class(current_class):
                i += 1
                continue
                
            if not is_valid_list_class(next_class):
                i += 1
                continue

            current_level = get_level(current_class)
            next_level = get_level(next_class)

            if next_level > current_level:
                current.append(next.extract())

            elif next_level < current_level:
                parent = current.find_parent(HTML_LIST_TAGS)
                while parent:
                    parent_level = get_level(parent.get("class")[0])

                    if parent_level <= next_level:
                        break  # Correct level reached

                    # If not at the right level, move back up one level
                    parent = parent.find_parent(HTML_LIST_TAGS)

                if parent:
                    parent.insert_after(next.extract())
            else:
                i += 1

            i += 1

        return soup

    soup = unwrap_list_items(soup)
    soup = make_lists_from_divs(soup)
    soup = nest_lists(soup)

    return soup


def create_code_blocks(soup: BeautifulSoup, css_src: list[str]):
    """
    Creates code blocks for code-like data, identified as:
    - Sequences of spans that apply a CSS class which applies a monospaced font
    - The contents of PL blocks
    """

    def create_code_block(lines: list[str]):
        pre = soup.new_tag("pre")
        code = soup.new_tag("code")

        # Preserve code-like structure
        plaintext = f'{"".join(lines)}\n'

        # Create <pre><code>{...contents...}</code></pre> structure
        code.append(plaintext)
        code["class"] = "language-json"  # Add JSON hint
        pre.append(code)

        return pre

    def make_block(soup: BeautifulSoup, current_group: list[Tag]):
        """Makes a code block out of the paragraphs contained in `current_group`, then empties `current_group` to prepare for future code blocks"""
        if len(current_group) < 2:
            # There aren't enough elements to justify making a code block
            return []

        plaintext_lines = []

        # Get paragraphs' lines
        for p in current_group:
            text = p.find("span").get_text(strip=False)

            # Replace any newlines in the middle of the string (not at the beginning or the end) with spaces
            middle_newline_regex = r"(?<!^)\n(?!$)"
            text = re.sub(middle_newline_regex, " ", text)

            plaintext_lines.append(f"{text}\n")

        # Create code block from paragraphs' lines
        code_block = create_code_block(plaintext_lines)

        # Replace paragraph sequence with code blocks, if it exists
        if code_block:
            first_paragraph = current_group[0]
            first_paragraph.insert_before(code_block)

            for paragraph in current_group:
                paragraph.decompose()

        # Prepare current_group for subsequent code blocks
        current_group = []

        return current_group

    def handle_monospaced_span_sequences_within_div(
        soup: BeautifulSoup,
        div: Tag,
        monospaced_span_classes: list[str],
        monospaced_div_classes: list[str],
    ):
        """When the div contains a series of spans, each of which applies a monospaced class"""
        # Ensure only applicable divs are affected
        if not any(cls in monospaced_div_classes for cls in div.get("class", [])):
            return soup

        children = list(div.children)
        current_group: list[Tag] = []

        for child in children:
            if isinstance(child, Tag) and child.name == "p":
                spans = child.find_all("span", recursive=False)

                if (
                    len(spans) == 1
                    and spans[0].has_attr("class")
                    and any(cls in monospaced_span_classes for cls in spans[0]["class"])
                ):
                    current_group.append(child)
                    continue

            current_group = make_block(soup, current_group)

        current_group = make_block(soup, current_group)

        return soup

    def handle_monospaced_span_sequences_outside_div(
        soup: BeautifulSoup, monospaced_classes: list[str]
    ):
        """Some monospaced span sequences occur outside of divs. Enclose these within code blocks."""

        for element in soup.find_all(recursive=False):
            for child in element.find_all(recursive=False):
                grandchildren = child.find_all(recursive=False)

                current_group: list[Tag] = []
                i = 0

                while i < len(grandchildren):
                    grandchild = grandchildren[i]

                    is_grandchild_paragraph = (
                        isinstance(grandchild, Tag) and grandchild.name == "p"
                    )

                    if not is_grandchild_paragraph:
                        current_group = make_block(
                            soup, current_group
                        )  # This may be an end of a sequence, so make the block
                        i += 1
                        continue

                    elements = [
                        elem
                        for elem in list(grandchild.children)
                        if not is_whitespace_navstr(elem)
                    ]  # Exclude NavigableStrings with just whitespace, since their content doesn't matter as far as document structure goes and they would only trigger false positives for the check that determines if the current paragraph is not in a sequence of paragraphs containing elements of a code block

                    spans = grandchild.find_all(
                        "span",
                        attrs={
                            "class": lambda cls: cls
                            and any(
                                monospaced_class in cls
                                for monospaced_class in monospaced_classes
                            )
                        },
                    )

                    if len(spans) != len(elements):
                        # If the number of filtered elements doesn't match the number of spans in `spans`, there is more than just a monospaced span here, so it can't be part of the code block.
                        current_group = make_block(
                            soup, current_group
                        )  # This may be an end of a sequence too, so make the block
                        i += 1
                        continue  # If the grandchild consists of more than just spans, it isn't part of a block of code

                    current_group.append(grandchild)

                    i += 1

        return soup

    def handle_whole_divs(soup: BeautifulSoup, div: Tag, classes):
        """When the whole div applies a monospaced style"""
        if div is None or div.parent is None or not hasattr(div, "get"):
            return soup

        div_classes = div.get("class", [])

        if (
            len(div_classes) == 1
            and div_classes[0] in classes
            and len(div.contents) > 0
        ):
            plaintext_lines: list[str] = []

            # Get just the text of the div's children
            for child in div.children:
                if isinstance(child, Tag) and child.name == "p":
                    text = child.get_text(strip=False)
                    plaintext_lines.append(text)

                elif isinstance(child, NavigableString):
                    plaintext_lines.append(str(child))

                elif isinstance(child, Tag):
                    plaintext_lines.append(child.get_text(strip=False))

            # Remove excess newlines
            plaintext_lines = [line for line in plaintext_lines if line.strip()]

            # Replace old div with new code block
            code_block = create_code_block(plaintext_lines)

            div.insert_before(code_block)
            div.decompose()

        return soup

    def cleanup_divs(soup: BeautifulSoup):
        """There will be redundant divs leftover that only contain code blocks. Remove those divs, preserving the contents."""
        for div in soup.find_all("div"):
            children: list[Tag] = [
                child
                for child in div.contents
                if not (isinstance(child, NavigableString) and child.strip == "")
            ]

            if (
                len(children) == 1
                and isinstance(children[0], Tag)
                and children[0].name == "pre"
            ):
                div.unwrap()

        return soup

    def cleanup_excess_newlines(soup: BeautifulSoup):
        """Remove excessive newlines from some code blocks"""
        for pre in soup.find_all("pre"):
            if not (
                len(pre.contents) == 1
                and isinstance(pre.contents[0], Tag)
                and pre.contents[0].name == "code"
            ):
                continue  # This is not a <pre><code> block

            code: Tag = pre.contents[0]

            # Work only on code blocks that need to have their contents modified
            lines = [line for line in code.get_text()]
            lines_stripped = [
                line for line in code.get_text().splitlines() if line.strip()
            ]

            if len(lines) == len(lines_stripped):
                continue  # This code block is already formatted correctly

            # Re-form the body of the code block
            contents = "\n" + "\n".join(lines_stripped) + "\n"

            # Replace contents
            code.clear()
            code.append(NavigableString(contents))

        return soup

    monospaced_classes = get_css_classes("monospaced", css_src)
    monospaced_classes_for_divs = ["PL"]
    classes_to_target_for_span_consolidation = ["B1plus", "EX", "NO"]
    divs = soup.find_all("div")

    # Process the divs
    for div in divs[:]:
        soup = handle_monospaced_span_sequences_within_div(
            soup,
            div,
            monospaced_div_classes=classes_to_target_for_span_consolidation,
            monospaced_span_classes=monospaced_classes,
        )
        soup = handle_whole_divs(soup, div, monospaced_classes_for_divs)

    # Manipulations outside of divs
    soup = handle_monospaced_span_sequences_outside_div(soup, monospaced_classes)

    # Cleanup
    soup = cleanup_divs(soup)
    soup = cleanup_excess_newlines(soup)

    return soup


def handle_empty_tags(soup: BeautifulSoup):
    """Removes tags without any content, or whose content is just a newline"""
    tags = soup.find_all(True)

    # Tags like these are considered empty because they take the form of <tag/>, but they aren't actually empty
    non_empty_tags: list[str] = ["img"]

    def is_empty(tag: Tag):
        # Empty if no contents or only whitespace
        if tag.name in non_empty_tags:
            return False
        if not tag.contents:
            return True
        if all(
            (is_whitespace_navstr(contents))
            or (isinstance(contents, Tag) and is_empty(contents))
            for contents in tag.contents
        ):
            return True
        return False

    for tag in soup.find_all(True):
        # We want to avoid removing table cells, since they may contain empty content. Removing them would break the table structure.
        if tag.name in ["td", "th"]:
            continue

        if is_empty(tag):
            tag.decompose()

    return soup

def fix_references(soup: BeautifulSoup):
    """Fix references in the document"""
    for text_element in soup.find_all(string=True):
        REF_REGEX = r"\[(\d+)\](?![\(\[\{])"
        # give me all matches
        matches = re.findall(REF_REGEX, text_element)
        if matches:
            new_text = text_element
            for match in matches:
                # Replace [number] with [n.number]
                new_text = re.sub(r"\[" + match + r"\](?![\(\[\{])", f"[n.{match}]", new_text)

            # Replace the original text with the modified text
            text_element.replace_with(new_text)
    return soup

def remove_style_from_images(soup: BeautifulSoup):
    """Removes any style attributes from images"""
    for img in soup.find_all("img"):
        if img.has_attr("style"):
            del img["style"]
        if img.has_attr("alt"):
            del img["alt"]

        parent_tag = img.parent
        if parent_tag and parent_tag.name == "span" and parent_tag.has_attr("style"):
            # remove parent span if it only contains the image and has a style attribute and leave the img
            parent_tag.replace_with(img)

    return soup

def handle_figures_tables_structure(soup: BeautifulSoup):
    """Ensures that figures and tables captions are properly structured to follow ETSI guidelines"""
    fl_divs = soup.find_all("div", class_="FL")
    tf_divds = soup.find_all("div", class_="TF")
    th_divds = soup.find_all("div", class_="TH")

    for div in fl_divs + tf_divds + th_divds:
        if div.get("class") == ["FL"]:
            div_contents = [content for content in div.contents if not is_whitespace_navstr(content)]
            if len(div_contents) == 1 and isinstance(div_contents[0], Tag) and div_contents[0].name == "img":
                img = div_contents[0]
                div.replace_with(img)
        if div.get("class") == ["TF"] or div.get("class") == ["TH"]:
            # add leading and trailing ** to the text in the div
            text = div.get_text(strip=True)
            if text:
                new_text = f"**{text}**"
                new_tag = soup.new_tag("p")
                new_tag.string = new_text
                div.replace_with(new_tag)

    return soup

def clean_source_code_blocks(soup: BeautifulSoup):
    """
        Source codes have leading "textStartBlockquote" text and trailing "textEndBlockquote" text that should be removed. This function removes these texts and any extra newlines that may be left over from their removal.
        Also, if "textStartBlockquote" is present, the first line of the code block is ```text, not ```json, so this function also changes the language hint for code blocks that contain "textStartBlockquote" from JSON to text.
        Also it removes {{{{SPACE}}}} and replaces it with a single space.
    """
    for pre in soup.find_all("pre"):
        if not (
            len(pre.contents) == 1
            and isinstance(pre.contents[0], Tag)
            and pre.contents[0].name == "code"
        ):
            continue  # This is not a <pre><code> block

        code: Tag = pre.contents[0]
        code_text = code.get_text()

        if "textStartBlockquote" in code_text:
            # Change language hint to text
            code["class"] = "language-text"

            # Remove "textStartBlockquote" and "textEndBlockquote" and any newlines that may be left over from their removal
            cleaned_code_text = code_text.replace("textStartBlockquote", "").replace("textEndBlockquote", "")
            cleaned_code_text = "\n".join(line for line in cleaned_code_text.splitlines() if line.strip())
            code.string = cleaned_code_text
        if "jsonStartBlockquote" in code_text:
            # Remove "jsonStartBlockquote" and "jsonEndBlockquote" and any newlines that may be left over from their removal
            cleaned_code_text = code_text.replace("jsonStartBlockquote", "").replace("jsonEndBlockquote", "")
            cleaned_code_text = "\n".join(line for line in cleaned_code_text.splitlines() if line.strip())
            code.string = cleaned_code_text

    return soup


# endregion


def cleaning(soup: BeautifulSoup, css_src: bool):
    """
    ### Description
    Cleaning that takes place as a part of preprocessing
    - Make various changes to tags based on CSS class
    - Remove tags that have no content
    - Remove blockquotes
    - Normalize improperly formatted lists
    - Consolidate sequential spans and divs
    - Create code blocks where applicable
    - Fix lists

    ### Arguments
    - `soup`: the BeautifulSoup-parsed HTML source on which to operate.
    - `css_src`: a list of the CSS source files used by the HTML.
    """

    soup = ensure_correct_css_class_use(soup)

    soup = remove_example_tag_number_from_body(soup)

    soup = convert_source_code_divs(soup)

    soup = remove_redundant_parent_tags_when_children_have_classes(soup)

    soup = handle_blockquotes(soup)

    soup = handle_tags_for_empty_classes(soup, css_src)

    soup = consolidate_sequential_spans(soup, css_src)

    soup = format_lists(soup)

    soup = consolidate_div_sequences(soup)

    soup = handle_empty_tags(soup)

    soup = create_code_blocks(soup, css_src)

    soup = fix_references(soup)

    soup = remove_style_from_images(soup)

    soup = handle_figures_tables_structure(soup)

    soup = clean_source_code_blocks(soup)

    return soup
