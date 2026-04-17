import os, re, html, json
import shutil
from bs4 import BeautifulSoup, Tag, NavigableString
from ..time_book import get_timer

from src.utils import (
    apply_renaming_logic,
    get_dirty_filenames_mapping_with_expected_filenames,
    p_error,
    p_warning,
)

from src.constants import ABBREVIATION_CLASS, REFERENCE_MAPPING_MD_TO_HTML

normative_file = "clause-2"
informative_file = "clause-2"
files_with_references = [normative_file, informative_file]


# region Helpers
def remove_code_blocks_with_only_images(soup: BeautifulSoup):
    """
    Removes code elements inside paragraphs that contain only images, preserving the img elements.
    """
    paragraphs = soup.find_all("p")

    for paragraph in paragraphs:
        code_elements = paragraph.find_all("code")

        for code_element in code_elements:
            # Check if the code element contains only one child and it's an img
            children = [
                child for child in code_element.children if isinstance(child, Tag)
            ]
            if len(children) == 1 and children[0].name == "img":
                img_element = children[0]
                # Replace the code element with just the img element
                code_element.replace_with(img_element)

    return soup


def fix_toc_links(soup: BeautifulSoup, filenames_mapping: dict):
    """
    Fixes the table of contents links in the HTML by updating their href attributes
    based on the provided filenames mapping.
    """
    toc_links = soup.select("#TOC a")

    for link in toc_links:
        href = link.get("href", "")
        before_ash, after_ash = href.split("#", 1) if "#" in href else (href, "")
        if before_ash in filenames_mapping:
            link["href"] = f"{filenames_mapping[before_ash]}#{after_ash}"

    return soup


def get_document_title_from_html(html_dir: str, front_page: str = "front-page.html"):
    """
    Extract the document title from the front_page HTML file.
    """

    file_path = os.path.join(html_dir, front_page)
    if not os.path.exists(file_path):
        print(
            p_warning(
                f"Front page HTML file '{front_page}' not found in '{html_dir}'. Cannot extract document title."
            )
        )
        return None
    else:
        with open(file_path, "r", encoding="utf-8") as file:
            html_content = file.read()

        soup = BeautifulSoup(html_content, "html.parser")

        # Extract title, version, and date from expected spans in div.ZA
        div_za = soup.find("div", class_="ZA")
        title_span = None
        version_span = None
        date_span = None
        if div_za:
            p = div_za.find("p")
            if p:
                children = list(p.children)
                if len(children) >= 1:
                    title_span = children[0]
                if len(children) >= 2:
                    version_span = children[1]
                if len(children) >= 3:
                    date_span = children[2]
        if title_span or version_span or date_span:
            title_text = title_span.get_text(strip=True) if title_span else ""
            version_text = version_span.get_text(strip=True) if version_span else ""
            date_text = date_span.get_text(strip=True) if date_span else ""
            if title_text or version_text:
                # return title_text + " " + version_text + " " + date_text
                parts = [part for part in (title_text, version_text, date_text) if part]
                return " ".join(parts)

    return None


def update_toc_title(soup: BeautifulSoup, document_title: str):
    """Update the TOC title with the value in document_title."""
    if not document_title:
        return soup

    toc_title_link = soup.select_one("#TOC h1 a")
    if toc_title_link:
        toc_title_link.clear()
        toc_title_link.append(NavigableString(document_title))

    return soup


def fix_ex_json_spacing(soup: BeautifulSoup):
    """Removes `<br />` tags from the ends of lines containing JSON data. These tags add too much space between lines."""
    examples = soup.find_all("div", class_="EX")

    for example in examples:
        for br_tag in example.find_all("br"):
            br_tag.decompose()

    return soup


def convert_source_code_blocks_to_html(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Convert <div class="Source_Code"> elements (and EX/NO body divs whose content
    consists entirely of <span class="HTML-Sample"> runs) into the canonical
    pandoc-style structure:

        <div class="sourceCode" id="cbN">
          <pre class="sourceCode json">
            <code class="sourceCode json">
              <span id="cbN-1"><a aria-hidden="true" href="#cbN-1" tabindex="-1"></a>LINE\n</span>
              ...
            </code>
          </pre>
        </div>

    Consecutive sibling Source_Code divs are merged into a single block.
    When a jsonStartBlockquote/jsonEndBlockquote vanished run is already present in the dirty HTML
    (from the HTML→DOCX→HTML round-trip) it will appear as plain text and the
    Source_Code / HTML-Sample heuristics are sufficient to detect the block
    boundaries without additional markers.
    """
    cb_counter = [0]  # mutable so inner helpers can increment it

    def next_cb_id() -> str:
        cb_counter[0] += 1
        return f"cb{cb_counter[0]}"

    def extract_code_text(container: Tag) -> str:
        """Collect raw text from HTML-Sample spans; treat <br>-containing spans as newlines."""
        parts = []
        for child in container.children:
            if isinstance(child, NavigableString):
                continue  # ignore bare whitespace text nodes between spans
            if not isinstance(child, Tag):
                continue
            if child.name == "span" and "HTML-Sample" in child.get("class", []):
                if child.find("br"):
                    parts.append("\n")
                else:
                    parts.append(child.get_text().replace("\xa0", " "))
            elif child.name == "br":
                parts.append("\n")
        return "".join(parts)

    def all_children_are_html_sample(div: Tag) -> bool:
        """Return True iff every non-whitespace child is an HTML-Sample span or a bare <br>."""
        has_any = False
        for child in div.children:
            if isinstance(child, NavigableString):
                if child.strip():  # real text node – not pure code
                    return False
            elif isinstance(child, Tag):
                classes = child.get("class", [])
                if child.name == "span" and "HTML-Sample" in classes:
                    has_any = True
                elif child.name == "br":
                    pass  # line-break placeholder – OK
                else:
                    return False
        return has_any

    def build_block(code_text: str) -> Tag:
        """Return a sourceCode div tree from raw (newline-delimited) code text."""
        cb_id = next_cb_id()
        lines = code_text.split("\n")
        # Drop a trailing blank line produced by a final \n
        if lines and not lines[-1].strip():
            lines = lines[:-1]

        code_tag = soup.new_tag("code", attrs={"class": "sourceCode json"})
        for i, line in enumerate(lines, 1):
            line_span = soup.new_tag("span", attrs={"id": f"{cb_id}-{i}"})
            anchor = soup.new_tag(
                "a",
                attrs={"aria-hidden": "true", "href": f"#{cb_id}-{i}", "tabindex": "-1"},
            )
            line_span.append(anchor)
            line_span.append(NavigableString(line + "\n"))
            code_tag.append(line_span)

        pre_tag = soup.new_tag("pre", attrs={"class": "sourceCode json"})
        pre_tag.append(code_tag)

        div_tag = soup.new_tag("div", attrs={"class": "sourceCode", "id": cb_id})
        div_tag.append(pre_tag)
        return div_tag

    # ── 1. Standalone Source_Code divs (merge consecutive siblings) ──────────
    seen: set[int] = set()
    for div in list(soup.find_all("div", class_="Source_Code")):
        if id(div) in seen:
            continue

        group = [div]
        seen.add(id(div))
        nxt = div.next_sibling
        while nxt:
            if isinstance(nxt, NavigableString) and not nxt.strip():
                nxt = nxt.next_sibling
                continue
            if isinstance(nxt, Tag) and "Source_Code" in nxt.get("class", []):
                seen.add(id(nxt))
                group.append(nxt)
                nxt = nxt.next_sibling
            else:
                break

        code_parts: list[str] = []
        for g in group:
            text = extract_code_text(g)
            if code_parts and not code_parts[-1].endswith("\n"):
                code_parts.append("\n")
            code_parts.append(text)

        block = build_block("".join(code_parts))
        div.replace_with(block)
        for g in group[1:]:
            g.decompose()

    # ── 2. EX / NO / TAN body divs whose entire content is code spans ─────────
    EX_CLASSES = {"EX", "NO", "TAN"}
    for ex_div in list(soup.find_all("div", class_=lambda c: c and bool(set(c) & EX_CLASSES))):
        # Collect meaningful (non-whitespace) children
        children = [
            c for c in ex_div.children
            if not (isinstance(c, NavigableString) and not c.strip())
        ]
        if len(children) != 2:  # expect exactly label-div + body-div
            continue

        label_div, body_div = children[0], children[1]
        if not (isinstance(label_div, Tag) and isinstance(body_div, Tag)):
            continue

        if not all_children_are_html_sample(body_div):
            continue  # mixed content – leave as-is

        code_text = extract_code_text(body_div)
        block = build_block(code_text)
        body_div.clear()
        body_div.append(block)

    return soup


def unwrap_gt_lt_code_tags(soup: BeautifulSoup):
    """
    #### Functionality
    Unwrap the code tags to preserve their contents without any changes to how they render, maintaining the `&lt;` and `&gt;` to maintain `<` and `>` respectively as plaintext.

    #### Explanation of Necessity
    During preprocessing, sections of text marked by a beginning `<` and an ending `>` needed to be enclosed in code blocks for Pandoc to preserve the text.
    """
    # codes = soup.find_all("code", lambda tag: tag.parent and tag.parent.name != "pre")
    codes = soup.select("code:not(em > code)")

    for code in codes:
        if code.parent and code.parent.name == "pre":
            span_text_only_children = code.find_all(
                lambda tag: isinstance(tag, Tag)
                and tag.name == "span"
                and len(tag.contents) == 1
                and isinstance(tag.contents[0], NavigableString)
            )
            for child in span_text_only_children:
                raw_text = (
                    child.get_text().replace("`&lt;", "&lt;").replace("&gt;`", "&gt;")
                )
                text = NavigableString(html.unescape(raw_text))
                child.contents[0].replace_with(text)
        else:
            text = NavigableString(html.unescape(code.get_text()))
            code.insert_before(text)
            code.decompose()

    return soup


def format_references(soup: BeautifulSoup):
    """
    Since references are wrapped in the `EX` class, and they were impacted during HTML-Markdown preprocessing.

    Converts references to the expected format (`<div id={...} class="EX"><span></span><span></span></div>`) to ensure they are displayed correctly.
    """
    EXAMPLE_CLASS = "EX"
    examples = soup.find_all("div", class_=EXAMPLE_CLASS, id=False)

    for example in examples:
        # For now, these example divs follow the usual format of having all the contents contained within two child divs. Unwrap these divs.
        for child in list(example.children):
            if child.name == "div":
                child.unwrap()

        # Setup
        paragraphs = example.find_all("p", recursive=False)
        references: list[Tag] = []

        for paragraph in paragraphs:
            if not paragraph.contents:
                continue

            first_child = paragraph.contents[0]

            # Check that the first child is an empty <span>, otherwise skip this paragraph
            if not (
                isinstance(first_child, Tag)
                and first_child.name == "span"
                and first_child.get("id")
                and first_child.get_text() == ""
            ):
                continue

            ref_id = first_child.get("id", "")
            second_child = paragraph.contents[1]
            tag, remamining_text = second_child.split("] ")
            tag += "] "  ## leaving this trailing space because we need to check if this is needed when generating a docx
            tag = tag.replace("[n.", "[")

            first_child.extract()
            second_child.extract()

            # Prepare new parent div and child spans
            parent_div = soup.new_tag(
                "div", attrs={"id": ref_id, "class": EXAMPLE_CLASS}
            )
            tag_span = soup.new_tag("span")
            body_span = soup.new_tag("span")
            body_span.append(NavigableString(remamining_text))

            # Add tag
            tag_span.append(NavigableString(tag))

            # Add body contents
            for contents in list(paragraph.contents):
                body_span.append(contents)

            # Append spans to div, and div to references list
            parent_div.append(tag_span)
            parent_div.append(body_span)
            references.append(parent_div)

        # Switch references
        for reference in references:
            example.insert_before(reference)
        example.decompose()

    return soup


def handle_ew_div(soup: BeautifulSoup):
    """Expands a single div applying the `EW` class to a series of paragraphs, each of which containing an abbreviation and its meaning, into a series of divs each dedicated to a single abbreviation. Also adds a tab between the abbreviation and its meaning to ensure proper indentation."""
    consolidated_abbreviations = soup.find("div", attrs={"class": ABBREVIATION_CLASS})

    if not consolidated_abbreviations:
        return soup

    paragraphs = consolidated_abbreviations.find_all("p")

    for para in reversed(
        paragraphs
    ):  # Reverse the order to make sure the abbreviations end up in the correct order
        abbreviation, meaning = para.get_text().split(" ", 1)

        abbr_div = soup.new_tag("div")
        abbr_div.append(NavigableString(abbreviation))

        meaning_div = soup.new_tag("div")
        meaning_div.append(NavigableString(meaning))

        div_replacement = soup.new_tag("div", attrs={"class": ABBREVIATION_CLASS})
        div_replacement.append(abbr_div)
        div_replacement.append(meaning_div)

        consolidated_abbreviations.insert_after(div_replacement)
        consolidated_abbreviations.insert_after(
            NavigableString("\n")
        )  # For readability in the raw HTML, has no visual effect when rendered

    consolidated_abbreviations.decompose()

    return soup


def format_examples_and_notes(soup: BeautifulSoup):
    """Restores the expected HTML structure to examples and notes, which have come in from the Markdown as sequential blocks of code enclosed three times each in `<blockquote>`s."""

    def get_label_text_and_class(para: Tag):
        """Get the label text from the paragraph and determine the class to assign to the div"""
        text = para.contents[0].split(":")[0] + ":"
        remaining_text = (
            para.contents[0].split(": ")[1] if ": " in para.contents[0] else ""
        )
        cls = ""

        if "[!tip]" in text:
            cls = "EX"
        else:
            cls = "TAN" if para.find_parent("td") else "NO"

        text = text.replace("[!note] ", "").replace("[!tip] ", "")

        remaining_contents = para.contents[1:]

        span_remove_number = None
        if remaining_contents and remaining_contents[0].name == "span" and remaining_contents[0].get("class") == ["remove-number"]:
            span_remove_number = remaining_contents[0]
            remaining_contents = remaining_contents[1:]

        if remaining_text:
            remaining_contents.insert(0, NavigableString(remaining_text))
        return text, span_remove_number, cls, remaining_contents

    # Take only the top-level blockquotes to simplify logic
    blockquotes = [
        bq for bq in soup.find_all("blockquote") if not bq.find_parent("blockquote")
    ]

    for blockquote in reversed(blockquotes):
        label_para = blockquote.find("p")

        if not label_para:
            continue

        label_text, span_remove_number, label_class, remaining_contents = get_label_text_and_class(
            label_para
        )

        new_parent_div = soup.new_tag("div", attrs={"class": label_class})

        # Process label
        label_div = soup.new_tag("div")

        new_label_para = soup.new_tag("p")
        new_label_para.append(NavigableString(label_text))
        if span_remove_number:
            new_label_para.append(span_remove_number)

        label_div.append(new_label_para)
        new_parent_div.append(label_div)

        # Process body
        body_div = soup.new_tag("div")
        if (
            remaining_contents
        ):  # this happens when there is not an empty line after the [!note] or [!tip], better to do here because in md we have gridtables to take care of
            para_container = soup.new_tag("p")
            for content in remaining_contents:
                para_container.append(content)
            body_div.append(para_container)
        else:
            current = blockquote.next_sibling

            while current:
                if current.name == "blockquote":
                    # Finished gathering body elements
                    current.decompose()
                    break

                next_sibling = current.next_sibling
                current.extract()
                body_div.append(current)
                current = next_sibling

        new_parent_div.append(body_div)

        # Finish processing
        blockquote.replace_with(new_parent_div)

    return soup


def format_tables(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Formats tables in the HTML content to ensure proper structure and styling.

    Args:
        soup (BeautifulSoup): The BeautifulSoup object representing the HTML content.
    Returns:
        BeautifulSoup: The modified BeautifulSoup object with formatted tables.
    """

    # add stripes to table rows
    tables = soup.find_all("table", class_=lambda x: x != "no-table-stripes")
    for table in tables:
        tbody = table.find("tbody")
        trs = tbody.find_all("tr") if tbody else []
        tdsFirstRow = trs[0].find_all("td") if trs else []
        isNewRow = True
        # if the grid tables use colspans, we apply stripes by checking the number of tds in each row
        # In a series of rows that belong to the same logical row, only the first row will have the full number of tds
        for tr in trs:
            tds = tr.find_all("td")
            if len(tds) == len(tdsFirstRow):
                isNewRow = not isNewRow
            if isNewRow:
                existing_classes = tr.get("class", [])
                if "bg-striped-row" not in existing_classes:
                    tr["class"] = existing_classes + ["bg-striped-row"]
    return soup


def format_front_page(soup: BeautifulSoup) -> BeautifulSoup:
    ZA = soup.find_all("div", class_="ZA")
    try:
        p = ZA[0].find("p")
        children = list(p.children)
        try:
            # TITLE IN HEADER
            header = children[0]
            header["data-replace"] = "WORKITEMNAME"
        except IndexError:
            print(p_warning("front-page is missing WORKITEMNAME information."))
        # Version in HEADER
        try:
            version = children[1]
            new_span = soup.new_tag("span")
            version.wrap(new_span)
            new_span["data-replace"] = "VERSION_NO"
        except IndexError:
            print(p_warning("front-page is missing VERSION_NO information."))
        # DATE IN HEADER
        try:
            date = children[2]
            text = date.get_text(strip=True)
            text = text.replace("(", "").replace(")", "")
            open_bracket = NavigableString("(")
            date_text = new_span = soup.new_tag("span")
            date_text["data-replace"] = "DATE"
            date_text.string = text
            close_bracket = NavigableString(")")
            date.clear()
            date.append(open_bracket)
            date.append(date_text)
            date.append(close_bracket)
        except IndexError:
            print(p_warning("front-page is missing DATE information."))
    except IndexError:
        print(
            p_warning(
                "front-page is missing the section with WORKITEMNAME, VERSION_NO, and DATE information."
            )
        )

    ZT = soup.find_all("div", class_="ZT")
    try:
        # first is title
        ZT[0]["data-replace"] = "{{TITLE}}"
    except IndexError:
        print(p_warning("front-page is missing TITLE information."))
    try:
        # second is part
        ZT[1]["data-replace"] = "{{PART}}"
    except IndexError:
        print(p_warning("front-page is missing PART information."))
    try:
        # third is subpart
        ZT[2]["data-replace"] = "{{SUBPART}}"
    except IndexError:
        print(p_warning("front-page is missing SUBPART information."))
    try:
        # fourth is release
        ZT[3]["data-replace"] = "{{RELEASE}}"
    except IndexError:
        print(p_warning("front-page is missing RELEASE information."))

    ZB = soup.find_all("div", class_="ZB")
    try:
        ZB[0]["data-replace"] = "{{TYPEDOCUMENT}}"
    except IndexError:
        print(p_warning("front-page is missing TYPEDOCUMENT information."))

    TAC = soup.find_all("div", class_="TAC")
    try:
        children = list(TAC[0].children)
        try:
            # SECOND is WORKITEM
            workitem = children[3]
            workitem["data-replace"] = "{{WORKITEM}}"
        except IndexError:
            print(p_warning("front-page is missing WORKITEM information."))
        # FOURTH is KEYWORDS
        try:
            keywords = children[7]
            keywords["data-replace"] = "{{KEYWORDS}}"
        except IndexError:
            print(p_warning("front-page is missing KEYWORDS information."))
    except IndexError:
        print(
            p_warning(
                "front-page is missing the section with WORKITEM and KEYWORDS information."
            )
        )

    return soup


def add_links_to_references_in_text(soup):
    def reform_broken_links_in_text(soup: BeautifulSoup):
        """
        Fix reference links throughout the text that are effectively just plaintext. Reform the link.

        Broken reference tags take the following form:

        ```
        <span>                                <span>
            [{reference tag}]       OR            \[{reference tag}\]
        </span>                               </span>
        ```
        """
        # Some links are already properly formed, so they don't need anything done to them. Such links are surrounded by an extra pair of brackets, so add a negative lookahead and a negative lookbehind to exclude those outer brackets.
        # Reference must start with i. or n. to be valid (use non-capturing group for prefix)
        BAD_LINK_REGEX = r"^\\?\[{1}((?:i\.|n\.)[A-Za-z0-9]+)\\?\](?!\])(.*?)$"

        spans = soup.find_all("span", attrs={None})

        for span in spans:
            text = span.get_text()
            match = re.search(BAD_LINK_REGEX, text)

            if not match:
                continue

            tag_contents = match.group(1)
            after_contents = (
                NavigableString(match.group(2)) if match.group(2).strip() else None
            )

            is_informative = tag_contents.startswith("i.")

            ref_file = informative_file if is_informative else normative_file
            # tag_contents already contains the full ref_id (e.g., "i.6" or "n.5")
            ref_id = tag_contents
            link = f"{ref_file}.html#{ref_id}"

            a = soup.new_tag("a", attrs={"href": link})
            a.append(f"[{tag_contents}]")

            span.replace_with(a)

            # After the <a>, add any miscellaneous text that was erroneously part of the link
            if after_contents:
                a.insert_after(after_contents)

        return soup

    # Reference pattern: must start with i. or n. followed by alphanumeric characters
    # This ensures [n] or [123] are not mistaken for references
    REG_REGEX = r"(?<!\[)\[(i\.|n\.)[A-Za-z0-9]+\]"

    def insert_link_with_reference(content, is_informative):
        with open(REFERENCE_MAPPING_MD_TO_HTML, "r") as ref_file:
            reference_mapping = json.load(ref_file)

        opening_bracket_index = content.find("[")
        closing_bracket_index = content.find("]") + 1
        internal_text = content[opening_bracket_index + 1 : closing_bracket_index - 1]
        internal_text = reference_mapping.get(internal_text, internal_text)

        # prepare the new <a> tag
        link = (
            f"{informative_file}.html#{internal_text}"
            if is_informative
            else f"{normative_file}.html#{internal_text}"
        )
        a = soup.new_tag("a", attrs={"href": link})
        a.append(f"[{internal_text.replace('n.', '')}]")
        return a

    def process_text_nodes(element):
        for content in list(element.contents):
            if isinstance(content, NavigableString):
                before_text = ""
                after_text = content
                while True:
                    match = re.search(REG_REGEX, after_text)
                    if match:
                        before_text = after_text[: match.start()]
                        after_text = after_text[match.end() :]
                        if before_text:
                            content.insert_before(NavigableString(before_text))

                        is_informative = match.group(1) == "i."
                        # replace content with the <a> tag
                        match_text = match.group(0)
                        a = insert_link_with_reference(match_text, is_informative)
                        content.insert_before(a)
                    else:
                        if after_text:
                            content.insert_before(NavigableString(after_text))
                        break

                content.extract()

            elif isinstance(content, Tag) and not content.name in ["a", "code"]:
                process_text_nodes(content)

    for element in soup.find_all(["p", "div"]):
        if element.name == "div" and element.get("id") == "list-of-references":
            continue  # It is the original reference in clause 2
        if (
            element.name == "p"
            and element.parent.name == "div"
            and element.parent.get("id") == "list-of-references"
        ):
            continue  # Skip paragraphs that are direct children of the reference list
        process_text_nodes(element)

    soup = reform_broken_links_in_text(soup)

    return soup


def move_dangling_brackets_out_of_links(soup: BeautifulSoup):
    """
    Move any dangling brackets that are part of links to the outside of the link tag.
    This is necessary for links that were improperly formatted and had brackets inside the link text.
    """

    for a in soup.find_all("a"):
        text = a.get_text()
        # Check for dangling brackets
        if (
            (text.startswith("(") and not text.endswith(")"))
            or (text.startswith("[") and not text.endswith("]"))
            or (text.startswith("{") and not text.endswith("}"))
        ):
            a.insert_before(
                NavigableString(text[0])
            )  # Add the opening bracket before the link
            a_text = text[1:]  # Remove the opening bracket from the link text
            a.string = a_text
        elif (
            (text.endswith(")") and not text.startswith("("))
            or (text.endswith("]") and not text.startswith("["))
            or (text.endswith("}") and not text.startswith("{"))
        ):
            a.insert_after(
                NavigableString(text[-1])
            )  # Add the closing bracket after the link
            a.string = text[:-1]  # Remove the closing bracket from the link text

    return soup


def remove_links_from_labels(soup: BeautifulSoup):
    """
    Remove links from label elements.
    """
    labels = soup.find_all("div", class_=["TF", "TH"])
    for label in labels:
        a_tag = label.find("a")
        if a_tag:
            a_tag.unwrap()
    return soup


def add_ids_to_labels(soup: BeautifulSoup):
    """
    Add ids to label elements if they don't have one.
    """
    labels = soup.find_all("div", class_=["TF", "TH"])
    for label in labels:
        if not label.get("id"):
            label_text = label.get_text().strip()
            id = label_text.split(":")[0].split(" ")[1]
            if label_text.startswith("Figure"):
                label.attrs["id"] = f"Figure_{id}"
            elif label_text.startswith("Table"):
                label.attrs["id"] = f"Table_{id}"
    return soup


def replace_dash_characters(soup: BeautifulSoup):
    """
    Replace dash characters in the a_tags and ids with the correct ones.
    """
    a_tags = soup.find_all("a")
    for a in a_tags:
        if a.string:
            a.string = a.string.replace("‑", "-").replace("—", "-")
            href = a.get("href", "")
            if href:
                a["href"] = href.replace("‑", "-").replace("—", "-")
    ids = soup.find_all(id=True)
    for element in ids:
        id = element.get("id", "")
        if id:
            element["id"] = id.replace("‑", "-").replace("—", "-")
    return soup


def move_figure_id_to_FL_elements(soup: BeautifulSoup):
    """
    Move the id attributes from figure elements to their parent FL elements.
    """
    figures = soup.find_all("div", class_="FL")

    for figure in figures:
        # get next sibling
        next_sibling = figure.find_next_sibling()
        # check that the very next sibling is a div with class TF
        if (
            next_sibling
            and next_sibling.name == "div"
            and "TF" in next_sibling["class"]
        ):
            id = next_sibling.get("id", "")
            figure.attrs["id"] = id
            next_sibling["id"] = None

    return soup


def shorten_toc_text(soup: BeautifulSoup):
    """
    Remove informative/normative from TOC only
    """
    # Find TOC element once to avoid repeated document searches
    toc = soup.select_one("#TOC")

    if toc:
        # Remove norm and inform elements from TOC first (reduces DOM size for subsequent searches)
        for elem in toc.find_all(class_=["norm", "inform"]):
            elem.decompose()

    # Update remaining norm elements (now only outside TOC)
    for elem in soup.find_all(class_="norm"):
        elem.string = "Normative"

    # Update remaining inform elements (now only outside TOC)
    for elem in soup.find_all(class_="inform"):
        elem.string = "Informative"

    return soup


def fix_custom_tags(soup: BeautifulSoup):
    """
    Fix custom tags in the HTML.
    """

    def notAnImage(href: str) -> bool:
        image_extensions = [".png", ".jpg", ".jpeg", ".svg"]
        return not any(href.endswith(ext) for ext in image_extensions)

    def remove_leading_punctuation(a: Tag, needle: str) -> None:
        if not a["href"].startswith("#" + needle):
            index = a["href"].find(needle)
            if index != -1 and index > 1:  # to account for the leading #
                new_href = f"#{a['href'][index:]}"
                a["href"] = new_href

        if not a.string.startswith(needle):
            index = a.string.find(needle)
            if index != -1 and index > 1:
                in_between_text = a["href"][1:index]  # exclude the leading #
                new_a_text = a.string[index:]
                a.string = new_a_text
                a.insert_before(NavigableString(in_between_text))

        return

    def remove_trailing_punctuation(a: Tag, needle: str) -> None:
        if not a["href"].endswith(needle):
            # find index of last occurrence of needle
            index = a["href"].rfind(needle)
            if index != -1 and index + len(needle) < len(a["href"]):
                new_href = a["href"][: index + len(needle)]
                a["href"] = new_href

        if not a.string.endswith(needle):
            # find index of last occurrence of needle
            index = a.string.rfind(needle)
            if index != -1 and index + len(needle) < len(a.string):
                remaining_text = a.string[index + len(needle) :]
                new_a_text = a.string[: index + len(needle)]
                a.string = new_a_text
                a.insert_after(NavigableString(remaining_text))
        return

    # Example: Change <custom-tag> to <div class="custom-tag">
    h1_tag = soup.find("h1", id=True)

    a_tags = soup.find_all("a")

    for a in a_tags:
        href = a.get("href", "")
        if href.find("+++below") != -1:
            is_table = "Table" in href
            remove_leading_punctuation(a, "Table+++" if is_table else "Figure+++")
            remove_trailing_punctuation(a, "+++below")

            href = a.get("href", "")
            a["title"] = href.replace("#", "")

            count_below = href.count("+++below")
            class_name = "TH" if is_table else "FL"
            next_nth_element = a
            for _ in range(count_below):
                next_nth_element = next_nth_element.find_next(
                    "div", class_=class_name, id=True
                )
            if next_nth_element:
                prefix = "Table" if is_table else "Figure"
                postfix = "+++below" * count_below
                string_to_be_replaced = f"{prefix}{postfix}"
                new_a_text = next_nth_element["id"].replace(prefix + "_", " ")
                a["href"] = href.replace(string_to_be_replaced, next_nth_element["id"])
                a.string = a.string.replace(postfix, new_a_text)
            else:
                # flash an error
                print(
                    p_error(f"Error: Found a broken custom tag in file {h1_tag.string}")
                )
                print(
                    p_error(
                        f"Error: No next element found for '{a.string}'. There are not any figures/tables above this tag."
                    )
                )
                os._exit(1)
        elif href.find("+++above") != -1:
            is_table = "Table" in href
            remove_leading_punctuation(a, "Table+++" if is_table else "Figure+++")
            remove_trailing_punctuation(a, "+++above")

            href = a.get("href", "")
            a["id"] = href.replace("#", "")

            count_above = href.count("+++above")
            class_name = "TH" if is_table else "FL"
            next_nth_element = a
            for _ in range(count_above):
                next_nth_element = next_nth_element.find_previous(
                    "div", class_=class_name, id=True
                )
            if next_nth_element:
                prefix = "Table" if is_table else "Figure"
                postfix = "+++above" * count_above
                string_to_be_replaced = f"{prefix}{postfix}"
                new_a_text = next_nth_element["id"].replace(prefix + "_", " ")
                a["href"] = href.replace(string_to_be_replaced, next_nth_element["id"])
                a.string = a.string.replace(postfix, new_a_text)
            else:
                # flash an error
                print(
                    p_error(f"Error: Found a broken custom tag in file {h1_tag.string}")
                )
                print(
                    p_error(
                        f"Error: No previous element found for '{a.string}'. There are not any figures/tables above this tag."
                    )
                )
                os._exit(1)
        elif (
            href.find("#") != -1 and href.find("root") != -1 and notAnImage(href)
        ):  # when root is used in md
            new_id_prefix = f"{h1_tag['id']}"
            a["href"] = href.replace("root", new_id_prefix)
            a.string = a.string.replace("root", new_id_prefix)
            a["title"] = a["id"]
        else:
            id = a.get("id", "")
            if id and "+++" in id:
                a["title"] = a["id"]
    return soup

def fix_lists(soup: BeautifulSoup):
    """
    Fix lists that have been improperly nested due to markdown conversion.
    """
    listitems = soup.find_all(["li"])

    for item in listitems:
        children = list(item.children)
        if len(children) == 1 and children[0].name in ["p"]:
            children[0].unwrap()

    return soup


def extract_images_from_html(soup: BeautifulSoup) -> dict:
    """
    Extracts image sources from the given HTML content.

    Args:
        html (str): The HTML content as a string.

    Returns:
        dict: A dictionary mapping image filenames to their full paths.
    """
    figures = soup.find_all("div", class_="FL")
    images_mapping = {}

    for fig in figures:
        id = fig.get("id", "")
        if id:
            img = fig.find("img")
            if img:
                src = img.get("src", "").replace("media/", "")
                images_mapping[id] = src
            figure_caption = fig.find("figcaption")
            if (
                figure_caption
            ):  # TODO: check if we might want to keep the caption instead of removing it
                figure_caption.decompose()

    return images_mapping, soup


def add_custom_link_to_images(
    soup: BeautifulSoup, images_mapping: dict
) -> BeautifulSoup:
    """
    Adds a custom link to images in the HTML content based on the provided images mapping.

    Args:
        html (str): The HTML content as a string.
        images_mapping (dict): A dictionary mapping image filenames to their full paths.

    Returns:
        str: The modified HTML content with custom links added to images.
    """
    # look for text that matches the pattern Figure+++<filename>
    a_tags = soup.find_all("a")
    for a in a_tags:
        href = a.get("href", "")
        if "Figure+++" in href:
            # Extract the filename from the href
            filename = href.split("+++")[1]
            if filename in images_mapping:
                image_info = images_mapping[filename]
                a["href"] = f"{image_info['file']}#{image_info['id']}"
                a.string = f"figure {image_info['id'].split('_')[1]}"
            else:
                raise ValueError(
                    f"ERROR: Image '{filename}' not found in images mapping. Are you sure it exists in the media folder and is used in the document?"
                )

    return soup


def fix_capitalization_in_links(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Ensures that the capitalization in the link text matches the capitalization in the href attribute.
    """
    a_tags = soup.find_all("a")
    span_clauses_tags = soup.find_all("span", class_="clauses-marker")
    for a in a_tags:
        text = a.get_text()
        if not text:
            continue

        if not text.startswith(("figure", "table", "clause", "annex")):
            continue

        # First case: it is the first word in a sentence
        if a.parent and a.parent.contents[0] == a:
            capitalized_text = text.capitalize()
            a.string = capitalized_text

        # Second case: it is after a period
        elif a.previous_sibling and isinstance(a.previous_sibling, NavigableString):
            prev_text = a.previous_sibling.strip()
            if (
                prev_text.endswith(".")
                or prev_text.endswith("!")
                or prev_text.endswith("?")
            ):
                capitalized_text = text.capitalize()
                a.string = capitalized_text
    for span in span_clauses_tags:
        text = span.get_text()
        if not text:
            continue
        if span.parent and span.parent.contents[0] == span:
            capitalized_text = text.capitalize()
            span.string = capitalized_text
        elif span.previous_sibling and isinstance(
            span.previous_sibling, NavigableString
        ):
            prev_text = span.previous_sibling.strip()
            if (
                prev_text.endswith(".")
                or prev_text.endswith("!")
                or prev_text.endswith("?")
            ):
                capitalized_text = text.capitalize()
                span.string = capitalized_text
    return soup


def add_toc_fetch_script_in_file(
    soup: BeautifulSoup, toc_filename: str
) -> BeautifulSoup:
    """
    Adds a script to dynamically load the Table of Contents from index.html.
    """
    toc = soup.select_one("#TOC")
    if toc:
        script = soup.new_tag("script")
        script.string = f"""
  fetch("{toc_filename}")
    .then(res => res.text())
    .then(html => {{
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, "text/html");
      const indexToc = doc.querySelector("#TOC");
      if (indexToc) {{
        document.getElementById("TOC").innerHTML = indexToc.innerHTML;
        
        // Re-initialize TOC functionality after loading new content
        if (typeof setupOnClickListeners === 'function') {{
          setupOnClickListeners();
        }}
        if (typeof scrollToClosestAnchorInTOC === 'function') {{
          scrollToClosestAnchorInTOC();
        }}
        if (typeof openCorrectPanelDependingOnStoredElement === 'function') {{
          openCorrectPanelDependingOnStoredElement();
        }}
        if (typeof fixFaultyTOCText === 'function') {{
          fixFaultyTOCText();
        }}
      }}
    }}).catch(error => {{
      console.error('Failed to load the table of contents:', error);
      const tocElement = document.getElementById("TOC");
      if (tocElement) {{
        tocElement.innerHTML = "<p>Table of contents could not be loaded.</p>";
      }}
      }});
"""
        toc.append(script)

    return soup


def remove_toc_content_from_file(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Empties the content of the TOC in the current soup.
    """
    toc = soup.select_one("#TOC")
    if toc:
        toc.clear()
    return soup


def clone_toc_in_file(soup: BeautifulSoup, toc_soup: BeautifulSoup) -> BeautifulSoup:
    """
    Clones the TOC from the provided TOC soup and inserts it into the current soup.
    """
    toc = soup.select_one("#TOC")
    if toc and toc_soup:
        from copy import deepcopy

        for element in toc_soup.select_one("#TOC").contents:
            toc.append(deepcopy(element))
    return soup


def cleanup_index_for_toc(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Keeps only the TOC content in the body of index.html while preserving head, CSS, and JavaScript.
    This prepares the file to be used as a source for fetching the TOC content in other files,
    or to be cloned into other files if --no-lazy-toc is used.
    """
    toc = soup.select_one("#TOC")
    body = soup.find("body")

    if toc and body:
        # Extract all script tags from body before clearing
        scripts = body.find_all("script")

        # Clear the body but keep the TOC
        body.clear()
        body.append(toc)

        # Re-add all scripts after the TOC
        for script in scripts:
            body.append(script)

    return soup

def fix_simple_table_headers(soup: BeautifulSoup) -> BeautifulSoup:
    """
    Ensure every 'th' in a 'thead' contains a div with the class 'TAH'.
    If no div exists, it wraps the content in a <div class="TAH">.
    If a div already exists, it forces its class to be exclusively 'TAH', 
    overwriting any other existing classes.
    """
    # Find all thead elements in the document
    theads = soup.find_all("thead")
    
    for thead in theads:
        # Find all th elements within this thead
        ths = thead.find_all("th")
        
        for th in ths:
            # Check if there are any divs inside this specific th
            divs = th.find_all("div")
            
            if not divs:
                # CASE 1: No div found. Create a new <div class="TAH">
                new_div = soup.new_tag("div", attrs={"class": "TAH"})
                
                # Move all the current content of the th (text or other tags) into the new div
                for child in list(th.contents):
                    new_div.append(child.extract())
                
                # Append the new div inside the th
                th.append(new_div)
                
            else:
                # CASE 2: At least one div exists. Force its class to be "TAH".
                # This automatically replaces any wrong class and leaves it as is if it's already "TAH".
                for div in divs:
                    div["class"] = ["TAH"]
            
    return soup


def postprocess(html_dir: str, no_lazy_toc: bool = False):
    """
    ### Description
    Iterates through the generated HTML files, applying various transformations to improve
    formatting, fix links, and ensure consistent styling. This includes:

    - Renaming files using the same logic applied to MD files
    - Formatting references properly in reference sections
    - Adding links to references mentioned in the text
    - Fixing table of contents links
    - Adjusting bracket placement around links
    - Removing excess spacing in code examples
    - Unwrapping code tags that should render as plaintext
    - Formatting abbreviation sections properly
    - Processing examples, notes and tips
    - Fixing image handling in code blocks
    - Adding and fixing IDs for figures and tables
    - Fixing custom tags for relative figure/table references
    - Normalizing dash characters in links and IDs
    - Ensuring proper capitalization in links
    - Creating cross-references for images

    ### Arguments
    - `html_dir`: Directory containing the HTML files to be processed
    """
    with get_timer().section("Postprocessing: 1 - Get dirty filenames mapping"):
        filenames_mapping = get_dirty_filenames_mapping_with_expected_filenames(
            html_dir
        )
    images_mapping = {}
    html_files = []
    processed_soups = []

    # Read and rename all HTML files
    with get_timer().section("Postprocessing: 2 - Read and Rename HTML Files"):
        for filename in os.listdir(html_dir):
            if filename.endswith(".html"):
                with open(
                    os.path.join(html_dir, filename), "r", encoding="utf-8"
                ) as file:
                    html_content = file.read()

                if filename == "index.html":
                    new_filename = filename
                else:
                    new_filename = apply_renaming_logic(html_content, filename, "html")

                os.rename(
                    os.path.join(html_dir, filename),
                    os.path.join(html_dir, new_filename),
                )

                html_files.append((new_filename, html_content))

    # First pass: process all HTML files while keeping soup in memory

    with get_timer().section("Postprocessing: 3 - First Pass - Process HTML Files"):
        document_title = get_document_title_from_html(html_dir)
        toc_filename = "index.html"
        fallback_toc_filename = "front-page.html"
        # If index.html doesn't exist, take front-page.html and make a copy named index.html
        if not any(f[0] == toc_filename for f in html_files):
            front_page_path = os.path.join(html_dir, fallback_toc_filename)
            index_path = os.path.join(html_dir, toc_filename)
            if os.path.exists(front_page_path):
                shutil.copyfile(front_page_path, index_path)
                with open(index_path, "r", encoding="utf-8") as file:
                    html_content = file.read()
                html_files.append((toc_filename, html_content))
        # Moves toc_filename at the end of the list to process it last
        html_files = sorted(html_files, key=lambda x: 1 if x[0] == toc_filename else 0)
        for new_filename, html_content in html_files:
            with get_timer().section(f"Parsing file: {new_filename}"):
                soup = BeautifulSoup(html_content, "html.parser")
                if new_filename != toc_filename:
                    soup = remove_toc_content_from_file(soup)
                    soup = move_dangling_brackets_out_of_links(soup)
                    if not no_lazy_toc:
                        soup = add_toc_fetch_script_in_file(soup, toc_filename)
                soup = remove_code_blocks_with_only_images(soup)
                soup = format_examples_and_notes(soup)
                soup = convert_source_code_blocks_to_html(soup)
                soup = format_tables(soup)
                soup = fix_simple_table_headers(soup)
                if new_filename == "front-page.html":
                    soup = format_front_page(soup)
                if (
                    new_filename.replace(".html", "") in files_with_references
                ):  # Reference-specific formatting
                    soup = format_references(soup)
                else:
                    soup = add_links_to_references_in_text(soup)
                # soup = fix_toc_links(soup, filenames_mapping)
                soup = fix_ex_json_spacing(soup)
                soup = unwrap_gt_lt_code_tags(soup)
                soup = handle_ew_div(soup)
                soup = remove_links_from_labels(soup)
                soup = add_ids_to_labels(soup)
                soup = replace_dash_characters(soup)
                soup = move_figure_id_to_FL_elements(soup)
                soup = fix_custom_tags(soup)
                soup = fix_lists(soup)
                images, soup = extract_images_from_html(soup)
                for image_id, image_src in images.items():
                    images_mapping[image_src] = {
                        "id": image_id,
                        "file": new_filename,
                    }
                if new_filename == toc_filename:
                    soup = shorten_toc_text(soup)
                    soup = fix_toc_links(soup, filenames_mapping)
                    soup = cleanup_index_for_toc(soup)
                    if document_title:
                        soup = update_toc_title(soup, document_title)
                # Keep soup in memory instead of writing and re-reading
                processed_soups.append((new_filename, soup))

    # Second pass: reuse soup objects already in memory
    with get_timer().section(
        "Postprocessing: 4 - Second Pass - Add Links and Write Files"
    ):
        for filename, soup in processed_soups:
            file_path = os.path.join(html_dir, filename)

            try:
                soup = add_custom_link_to_images(soup, images_mapping)
                soup = fix_capitalization_in_links(soup)
            except ValueError as e:
                print(p_error(f"Error in file {filename}:"))
                print(p_error(str(e)))
                os._exit(1)

            # Write the final file only once
            contents = soup.decode_contents()
            with open(file_path, "w", encoding="utf-8") as html:
                html.write(contents)

    if os.path.exists(REFERENCE_MAPPING_MD_TO_HTML):
        os.remove(REFERENCE_MAPPING_MD_TO_HTML)
