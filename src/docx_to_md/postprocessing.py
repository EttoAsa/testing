import os, re, html, json
import shutil
import sys
from bs4 import BeautifulSoup, Tag, NavigableString

DEBUG = True

def extract_image_info(soup: BeautifulSoup) -> BeautifulSoup:
    """Extract and process image information from alt text"""
    for img in soup.find_all("img"):
        alt_text = img.get("alt", "")
        content = alt_text.split("|")
        for item in content:
            if ":" in item:
                key, value = item.split(":", 1)
                if key == "alt":
                    img["alt"] = value
                elif key == "name":
                    img["src"] = f"media/{value}"
                elif key in ["width", "height"]:
                    try:
                        value = int(value)
                        img[key] = value
                    except ValueError:
                        value = None
    return soup

def format_examples_and_notes(soup: BeautifulSoup) -> BeautifulSoup:
    """
        Examples and notes are currently divided into multiple paragraphs, which makes it difficult to convert them to markdown.
        Every Example or note is structured as it follow:
            - First div with "EX" or "NO" class and containing the "startEXNO" marker
            - One div with "EX" or "NO" class and containing "EXAMPLE:" or "NOTE:" in the text
            - One or more HTML tags with content
            - Last div with "EX" or "NO" class and containing the "endEXNO" marker
        This function merges all these divs into a single div, which makes it easier to convert them to markdown.
        Also removes the "startEXNO" and "endEXNO" markers from the text.
    """
    start_marker = "startEXNO"
    end_marker = "endEXNO"
    heading_re = re.compile(r"^\s*(EXAMPLE|NOTE)\s*(\d+)?\s*:\s*", re.IGNORECASE)

    def is_example_or_note_div(tag: Tag) -> bool:
        if not isinstance(tag, Tag) or tag.name != "div":
            return False
        classes = tag.get("class", [])
        return "EX" in classes or "NO" in classes or "TAN" in classes

    def contains_marker(tag: Tag, marker: str) -> bool:
        return marker in tag.get_text(" ", strip=False)

    def remove_markers_from_tag(tag: Tag) -> None:
        for text_node in tag.find_all(string=re.compile(r"startEXNO|endEXNO")):
            cleaned = text_node.replace(start_marker, "").replace(end_marker, "")
            if cleaned:
                text_node.replace_with(cleaned)
            else:
                text_node.extract()

    def extract_heading_from_block(block: Tag) -> str:
        # Mutate only the very first element where the heading is expected.
        # No scanning over subsequent nodes to avoid unintended changes.
        if not block.contents:
            return ""

        first = block.contents[0]

        if isinstance(first, NavigableString):
            original_text = str(first)
            match = heading_re.match(original_text)
            if not match:
                return ""

            label = match.group(1).upper()
            number = match.group(2)
            heading = f"{label} {number}:" if number else f"{label}:"

            remaining = original_text[match.end():]
            if remaining:
                first.replace_with(remaining)
            else:
                first.extract()

            return heading

        if isinstance(first, Tag):
            first_text_node = first.string if isinstance(first.string, NavigableString) else None
            if first_text_node is None:
                return ""

            original_text = str(first_text_node)
            match = heading_re.match(original_text)
            if not match:
                return ""

            label = match.group(1).upper()
            number = match.group(2)
            heading = f"{label} {number}:" if number else f"{label}:"

            remaining = original_text[match.end():]
            if remaining:
                first_text_node.replace_with(remaining)
            else:
                first_text_node.extract()

            return heading

        return ""

    while True:
        start_div = soup.find(
            lambda t: is_example_or_note_div(t) and contains_marker(t, start_marker)
        )
        if start_div is None:
            break

        nodes_between = []
        end_div = None
        for sibling in list(start_div.next_siblings):
            if isinstance(sibling, Tag) and is_example_or_note_div(sibling) and contains_marker(sibling, end_marker):
                end_div = sibling
                break
            nodes_between.append(sibling)

        if end_div is None:
            remove_markers_from_tag(start_div)
            continue

        block_classes = start_div.get("class", [])
        if "EX" not in block_classes and "NO" not in block_classes and "TAN" not in block_classes:
            block_classes = ["EX"]

        wrapper_div = soup.new_tag("div")
        wrapper_div["class"] = block_classes

        title_div = soup.new_tag("div")
        content_div = soup.new_tag("div")

        heading = ""
        for node in nodes_between:
            if isinstance(node, Tag):
                heading = extract_heading_from_block(node)
                if heading:
                    break

        if not heading:
            heading = "EXAMPLE:" if "EX" in block_classes else "NOTE:"

        title_p = soup.new_tag("p")
        title_p.string = heading
        title_div.append(title_p)

        for node in nodes_between:
            if isinstance(node, NavigableString) and not node.strip():
                new_p = soup.new_tag("p")
                new_p.string = node
                content_div.append(new_p)
                continue

            extracted = node.extract()

            if isinstance(extracted, Tag) and extracted.name == "div":
                if extracted.get("class") and "Source_Code" in extracted.get("class"):
                    content_div.append(extracted)
                else:
                    # move children into a new <p> safely (use a copy of contents
                    # and extract() so nodes are moved, not duplicated/removed)
                    new_p = soup.new_tag("p")
                    for child in list(extracted.contents):
                        new_p.append(child.extract())
                    # original div is now empty; remove it
                    extracted.decompose()
                    content_div.append(new_p)
                    continue

            content_div.append(extracted)

        remove_markers_from_tag(content_div)

        wrapper_div.append(title_div)
        wrapper_div.append(content_div)

        start_div.insert_before(wrapper_div)
        start_div.decompose()
        end_div.decompose()

    return soup

def move_invisible_tildes_in_examples_notes(soup: BeautifulSoup) -> BeautifulSoup:
    """
        Move invisible tildes from the end of the example/note label to the beginning of the content.
        This is needed to ensure that the tildes are included in the markdown conversion, as they are used to indicate that the content is part of the example/note.
    """
    for div in soup.find_all("div", class_=lambda c: c and any(x in c for x in ["EX", "NO", "TAN"])):
        first_div = div.find("div")
        second_div = first_div.find_next_sibling("div") if first_div else None

        if not second_div:
            continue

        span_with_tilde = None
        for span in second_div.find_all("span"):
            if "~~~" in span.get_text() and "InvisibleText" in span.get("class", []):
                span_with_tilde = span
                break
        if span_with_tilde:
            # move it as last element of the first div
            span_with_tilde.extract()
            first_div.find('p').append(span_with_tilde)
    return soup

def remove_invisible_text_markers(soup: BeautifulSoup) -> BeautifulSoup:
    """
        Remove invisible text markers from the content.
        These markers are used to indicate that the content is part of the example/note, but they should not be included in the markdown conversion.
    """
    spans = soup.find_all("span", class_="InvisibleText")
    for span in spans:
        span.unwrap()
    return soup

def replace_invisible_text_links(soup: BeautifulSoup):
    """Replace links that point to content that is not present in the HTML with just the text of the link, since the link is replaced with the custom linking logic written in the original md (Clause+++, Table+++below etc)."""
    invisible_text_elements = soup.find_all("span", class_="InvisibleText")
    for element in invisible_text_elements:
        if "+++" not in element.get_text():
            continue

        # find next sibling a, that must be exactly the next element (ignoring whitespace)
        next_sibling = element.next_sibling
        if next_sibling and next_sibling.name == "a":
            next_sibling.decompose()
        
        element.unwrap()
    return soup


def remove_links_to_internal_content(soup: BeautifulSoup):
    """Remove links that point to content within the same document, since they are not used in md."""
    for a in soup.find_all("a", href=True):
        text = a.string
        lower_text = text.lower() if text else ""
        lower_href = a["href"].lower()
        if "clause" in lower_text or "figure" in lower_text or "table" in lower_text or "annex" in lower_text:
            a.unwrap()
        elif len(lower_href) == 41 and lower_href[0] == "#" and lower_href[1] == "x" and all(c in "0123456789abcdef" for c in lower_href[2:]):
            a.unwrap()
    
    clauses_markers_spans = soup.find_all("span", class_="clauses-marker")
    for span in clauses_markers_spans:
        span.unwrap()
    return soup

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python postprocessing.py <html_dirty_dir>")
        sys.exit(1)

    html_dirty_dir = sys.argv[1]

    # Process each HTML file in the html_dirty directory
    for filename in os.listdir(html_dirty_dir):
        if filename.endswith(".html"):
            file_path = os.path.join(html_dirty_dir, filename)

            with open(file_path, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")

            soup = extract_image_info(soup)
            soup = replace_invisible_text_links(soup)
            soup = remove_links_to_internal_content(soup)
            soup = format_examples_and_notes(soup)
            soup = move_invisible_tildes_in_examples_notes(soup)
            soup = remove_invisible_text_markers(soup)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(str(soup))