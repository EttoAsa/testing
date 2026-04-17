import re, json, os
from bs4 import BeautifulSoup, Tag, NavigableString

from src.constants import HEADER_TAGS, EXAMPLE_NOTE_CLASSES

from src.to_md.cleaning import cleaning as preprocess_cleaning


# ==============================================================================
# FIX TABELLE: Opzione Nucleare per forzare Pandoc a stampare gli Header
# ==============================================================================
def nuclear_table_header_fix(soup: BeautifulSoup):
    """
    Rimuove ogni possibile distrazione per Pandoc dalle intestazioni.
    Estrae solo il testo puro e lo inserisce in un <th> senza attributi o tag interni.
    Rimuove anche i <colgroup> che a volte forzano Pandoc a scartare gli header.
    """
    for table in soup.find_all("table"):
        # 1. Rimuovi i colgroup che possono corrompere il calcolo delle larghezze di Pandoc
        for colgroup in table.find_all("colgroup"):
            colgroup.decompose()
            
        thead = table.find("thead")
        if thead:
            thead.attrs = {} # Pulisci eventuali attributi del thead
            for tr in thead.find_all("tr"):
                tr.attrs = {}
                # Troviamo tutte le celle dell'header
                for cell in tr.find_all(["th", "td"]):
                    cell.name = "th" # Forza a th
                    cell.attrs = {}  # Rimuovi classi come TAH, stili, ecc.
                    
                    # 2. Estrai solo il testo crudo (es. "Resource Name")
                    # get_text ignora e distrugge automaticamente tutti i div, p, span e \n interni.
                    clean_text = cell.get_text(separator=" ", strip=True)
                    cell.clear()
                    cell.append(clean_text)

    return soup


# region Helpers
def remove_pandoc_toc(soup: BeautifulSoup):
    """
    Removes various elements added by Pandoc during conversion to HTML, but would only clutter the Markdown:
    - Table of Contents
    - Links to the CSS style sheets
    - Document headers and footers
    - Various buttons and switches
    - Editor tag enclosing the document's text

    These clutter the Markdown and will be added back in during conversion to HTML.
    """
    # Remove the Table of Contents
    toc = soup.find(id="TOC") or soup.find("nav", {"class": "toc"})
    if toc:
        toc.decompose()

    # Remove CSS links
    for link in soup.find_all("link", rel="stylesheet"):
        link.decompose()

    # Remove headers and footers
    for h_f in soup.select(".footer, .header"):
        h_f.decompose()

    # Handle div with id="editor", which contains the body contents. There is only one of its kind.
    editor_div = soup.find("div", attrs={"id": "editor"})
    body = soup.find("body")

    editor_div.extract()
    body.append(editor_div)
    editor_div.unwrap()

    for element in soup.select("button, label.switch, span.sider, input#editing"):
        element.decompose()

    return soup


def remove_flex(soup: BeautifulSoup):
    """Removes the `<flex>` and `<flex-item>` elements."""
    for flex in soup.find_all("flex"):
        # Decomposing the flex will cause the child <flex-item>s to likewise decompose
        flex.decompose()

    return soup


def format_abbreviations(soup: BeautifulSoup):
    """
    Correctly formatted abbreviations take this form and be in a series:

    `<div class="EW"><div>[abbreviation]</div><div>[meaning of abbreviation]</div></div>`

    Reformat this to have Pandoc produce a format easier to edit in the Markdown:

    `<div>class="EW">[abbreviation] [meaning]\\n[abbreviation] [meaning]\\n ... </div>`
    """
    ABBREVIATION_CLASS = "EW"

    def is_abbreviation(element):
        if not element.name or element.name != "div":
            return False

        div: Tag = element

        children = div.find_all(recursive=False)
        cls = div.get("class", [])

        if len(cls) != 1:
            return False

        cls = cls[0]
        if cls != ABBREVIATION_CLASS:
            return False

        if len(children) != 2:
            return False

        if children[0].name != "div" and children[1].name != "div":
            return False

        return True

    def make_abbreviation_paragraph(soup: BeautifulSoup, abbr_div: Tag):
        """From a single unprocessed abbreviation div, create a paragraph containing the abbreviation and its meaning separated by a single space"""
        children = abbr_div.find_all("div", recursive=False)
        abbreviation = children[0].get_text()
        meaning = children[1].get_text()

        abbreviation_paragraph = soup.new_tag("p")
        abbreviation_paragraph.append(NavigableString(f"{abbreviation} {meaning}"))

        return abbreviation_paragraph

    if soup.find("div", attrs={"class": ABBREVIATION_CLASS}) is None:
        return soup  # Nothing to do here

    elements: list[Tag] = soup.find_all(
        "div", attrs=lambda attrs: attrs and len(attrs) > 0
    )

    i = 0

    while i < len(elements):
        element = elements[i]

        if not is_abbreviation(element):
            i += 1
            continue

        consolidated_abbr_div = soup.new_tag(
            "div", attrs={"class": ABBREVIATION_CLASS}
        )  # Consolidate abbreviations in this div
        old_abbreviations: list[Tag] = []

        old_abbreviations.append(element)

        # Add the first abbreviation to the div
        abbr_para = make_abbreviation_paragraph(soup, abbr_div=element)
        consolidated_abbr_div.append(abbr_para)

        # Check if this div is in a series...
        is_in_series = False
        next_element = elements[i + 1]
        if is_abbreviation(next_element):
            is_in_series = True

        if not is_in_series:  # Insert the new div here and remove the old one
            element.insert_after(consolidated_abbr_div)
            element.decompose()

            i += 1
            continue

        # ...if so, continue processing divs...
        while i < len(elements) - 1:
            i += 1
            next_element = elements[i]

            if is_abbreviation(next_element):
                old_abbreviations.append(next_element)

                next_abbr_para = make_abbreviation_paragraph(
                    soup, abbr_div=next_element
                )
                consolidated_abbr_div.append(next_abbr_para)
            elif isinstance(next_element, NavigableString):
                continue  # Simply iterate over these, they don't matter as far as consolidation is concerned
            else:
                break  # Finished the sequence

        # ...and finally, add the new div and remove the old ones
        old_abbreviations[-1].insert_after(consolidated_abbr_div)
        for old_abbr in old_abbreviations:
            old_abbr.decompose()

        i += 1

    return soup


def format_notes_and_examples(soup: BeautifulSoup, is_cleanup: bool):
    """
    Does two things with examples and notes:
    1. Converts the inner divs to paragraphs
    2. If the cleanup flag is passed and if there are any code blocks that follow, move them into the main body of the tag
    """

    def convert_divs_to_paragraphs(
        soup: BeautifulSoup, classes: list[str] = EXAMPLE_NOTE_CLASSES
    ):
        # Only get divs that apply the EX or NO classes
        divs = soup.find_all(
            "div",
            class_=lambda class_attr: class_attr
            and any(cls in class_attr for cls in classes),
        )

        for div in divs:
            children = [child for child in div.children if isinstance(child, Tag)]

            # Only want divs with two classless child divs, one for the tag and one for the body
            child_is_classless_div: bool = (
                len(children) == 1  # One child..
                and children[0].name == "div"  # ...which is a div...
                and len(children[0].get("class", [])) == 0  # ...and is classless
            )

            children_are_classless_divs: bool = (
                len(children) == 2  # Two children...
                and children[0].name == "div"  # ...the first is a div...
                and len(children[0].get("class", [])) == 0  # ...with no class...
                and children[1].name == "div"  # ...and the second is a div...
                and len(children[1].get("class", [])) == 0  # ...with no class
            )

            if not child_is_classless_div and not children_are_classless_divs:
                continue

            if child_is_classless_div:
                child_div: Tag = children[0]
                child_paragraph: Tag = soup.new_tag("p")

                child_paragraph.extend(child_div.contents)

                child_div.insert_before(child_paragraph)
                child_div.decompose()

            if children_are_classless_divs:
                tag_div: Tag = children[0]
                body_div: Tag = children[1]

                tag_paragraph: Tag = soup.new_tag("p")
                body_paragraph: Tag = soup.new_tag("p")

                tag_paragraph.extend(tag_div.contents)
                body_paragraph.extend(body_div.contents)

                tag_div.insert_before(tag_paragraph)
                tag_div.decompose()

                body_div.insert_before(body_paragraph)
                body_div.decompose()

        return soup

    def move_code_blocks_to_body(
        soup: BeautifulSoup, classes: list[str] = EXAMPLE_NOTE_CLASSES
    ):
        divs = soup.find_all(
            "div",
            class_=lambda class_attr: class_attr
            and any(cls in class_attr for cls in classes),
        )

        for div in divs:
            div_class = div.get("class", [])[0]

            current = div.find_next_sibling()

            while current:
                # Skip siblings that aren't tags
                if not isinstance(current, Tag):
                    current = current.find_next_sibling()
                    continue

                current_class = (  # Get the class, if applicable
                    current.get("class", [])[0]
                    if current.get("class", []) and len(current.get("class", [])) == 1
                    else None
                )

                # Stop searching once it finds something to add to the body
                current_children = [
                    child for child in current.children if isinstance(child, Tag)
                ]
                if not current_children:
                    break  # This is a div without tags, not the kind of example or note to which the code block should be added

                child = current_children[0]

                is_successive_body_element = current_class == div_class
                is_code_block = current.name == "pre" and child.name == "code"

                if not (is_successive_body_element or is_code_block):
                    break

                next_sibling = current.find_next_sibling()

                # Handle code blocks
                if is_code_block:
                    div.append(current)

                # Handle successive elements
                elif is_successive_body_element:

                    current_tags = current.find_all(
                        lambda tag: tag if isinstance(tag, Tag) else None
                    )

                    if (
                        "EXAMPLE" in current_tags[0].get_text()
                        or "NOTE" in current_tags[0].get_text()
                    ):
                        break  # This is the beginning of another example or note

                    # Move the tags to the body
                    for tag in current_tags:
                        div.append(tag.extract())

                    # Remove the old div containing the body elements
                    current.extract()

                current = next_sibling

        return soup

    soup = convert_divs_to_paragraphs(soup)

    if is_cleanup:
        soup = move_code_blocks_to_body(soup)

    return soup


def simplify_headings(soup: BeautifulSoup, is_cleanup: bool):
    """
    Preprocess headings so that when Pandoc converts them to HTML, they are more human-manageable.
    """

    def update_filenames_in_ids(soup: BeautifulSoup):
        """Ensure that the filenames in inner links reflect the new filename. This involves removing any substrings `tab` from href attributes."""
        tags = soup.find_all(attrs={"href": True})

        for tag in tags:
            href_text = tag.get("href")

            while "tab" in href_text:
                before_tab, after_tab = href_text.split("tab", 1)
                href_text = f"{before_tab}{after_tab}"

                if "tab" not in href_text:
                    tag["href"] = href_text
                    break

        return soup

    headings = soup.find_all(HEADER_TAGS)

    mapping = {}

    for heading in headings:
        if heading.has_attr("data-number"):
            del heading["data-number"]

        if is_cleanup:
            old_id = heading["id"].replace("tab", "") if heading.has_attr("id") else ""
            heading_text = heading.get_text()
            annex_regex = r"^Annex\s+([A-Z])\s"
            clause_number_regex = r"^([A-Z]?\.?\d+(\.\d+)*)\s"
            if re.match(annex_regex, heading_text):
                match = re.match(annex_regex, heading_text)
                new_id = match.group(1)  # Extracts only the letter (A, B, C, etc.)
            elif re.match(clause_number_regex, heading_text):
                match = re.match(clause_number_regex, heading_text)
                new_id = match.group(1)  # Extracts the clause number
            else:
                # this is a clause without a number
                new_id = old_id
            if new_id != old_id:
                mapping[old_id] = new_id

        if heading.has_attr("id"):
            del heading["id"]

    soup = update_filenames_in_ids(soup)

    return soup, mapping


def edit_links_accordingly_with_expected_filenames(
    soup: BeautifulSoup, filenames_mapping: dict
):
    """
    Edit links in the document to point to the expected filenames based on the provided mapping.
    """
    for old_filename, new_filename in filenames_mapping.items():
        # This can happen when converting from docx to html then md, pandoc ads the "tab" word because the "\t" is in the title of a ETSI document
        if re.match(r"^\d+-tab", old_filename):
            old_filename = old_filename.replace("-tab", "-", 1)
        new_filename = (
            new_filename.replace("html", "md")
            if "html" in old_filename
            else new_filename.replace("md", "html")
        )
        # Update links in the soup
        for tag in soup.find_all(
            attrs={"href": lambda href: href and href.startswith(old_filename + "#")}
        ):
            # replace the portion of href left to the "#"
            tag["href"] = tag["href"].replace(old_filename, new_filename)

    return soup


def fix_link_to_headings_with_id_mapping(src: str, mapping: dict):
    """
    Fix the headings ID mapping in the HTML file using the mapping provided.
    """

    with open(src, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    for old_id, new_id in mapping.items():
        links = soup.find_all(
            attrs={"href": lambda href: href and href.endswith(f"#{old_id}")}
        )
        for link in links:
            link["href"] = link["href"].replace(old_id, new_id)

    content = soup.decode_contents()
    with open(src, "w", encoding="utf-8") as f:
        f.write(content)


def preprocess(
    src_path: str, dest_path: str, is_cleanup: bool, css_src, filenames_mapping: dict
):
    """
    ### Description
    Preprocessing mandatory for conversion from HTML to Markdown. **Operating on a single source HTML file**, performs the following tasks:
    
    1. Removes the table of contents, CSS links, headers/footers, buttons, and other Pandoc-generated elements
    2. Removes flex and flex-item elements that aren't needed in Markdown
    3. Formats abbreviations to have a more readable structure in Markdown
    4. Restructures notes and examples:
       - Converts inner divs to paragraphs
       - Moves related code blocks into the body of notes/examples (when cleanup flag is enabled)
    5. Simplifies headings by:
       - Removing data-number attributes
       - Generating cleaner IDs based on heading text
       - Creating a mapping between old and new IDs
    6. Updates links in the document to use expected filenames (when cleanup flag is enabled)
    7. Applies additional cleaning operations for "dirty" HTML sources
    
    ### Arguments
    - `src_path`: The absolute or relative path to the source HTML file
    - `dest_path`: The absolute or relative path where the processed HTML file will be saved
    - `is_cleanup`: `True` if additional formatting should be performed (when converting from "dirty" HTML), `False` otherwise
    - `css_src`: A list of absolute or relative paths to all source CSS files (needed for cleanup processing)
    - `filenames_mapping`: Dictionary mapping old filenames to expected filenames
    
    ### Returns
    - A dictionary mapping old heading IDs to new heading IDs
    """

    with open(src_path, "r", encoding="utf-8") as html:
        soup = BeautifulSoup(html, "html.parser")

    soup = remove_pandoc_toc(soup)
    soup = remove_flex(soup)

    if is_cleanup:
        soup = preprocess_cleaning(soup, css_src)
    else:
        # Preprocessing that is only applicable when converting "clean" HTML to Markdown
        soup = format_abbreviations(soup)

    soup = format_notes_and_examples(soup, is_cleanup)
    soup, mapping = simplify_headings(soup, is_cleanup)
    if is_cleanup:
        soup = edit_links_accordingly_with_expected_filenames(soup, filenames_mapping)

    # ==============================================================================
    # ESECUZIONE DEL FIX TABELLE: COME ULTIMISSIMA COSA!
    # ==============================================================================
    soup = nuclear_table_header_fix(soup)

    contents = soup.decode_contents()

    with open(dest_path, "w", encoding="utf-8") as html_new:
        html_new.write(contents)

    return mapping