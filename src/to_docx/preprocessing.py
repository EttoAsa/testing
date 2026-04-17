import code
import copy
import os
import re
from PIL import Image
from bs4 import BeautifulSoup, Tag, NavigableString
import xml.etree.ElementTree as ET

from src.constants import (
    EXAMPLE_NOTE_CLASSES,
    HANDLE_UNDERSCORE_CLASSES,
    HTML_BASIC_FORMAT_TAGS,
    NEWLINE_PLACEHOLDER,
    NO_SPACE,
    TAB_PLACEHOLDER,
    WITH_SPACE,
    WORD_A4_MAX_HEIGHT_PIXEL,
    WORD_A4_MAX_WIDTH_PIXEL,
)
from src.utils import combine_biu_classes, handle_html_consolidation, p_warning


# region Helpers
def is_reference(tag: Tag):
    """
    Determines whether a given tag is a reference. References are defined by this structure:

    ```
    <div class="EX" id="n.[number] or i.[number]">
      <span>
        [xx]
        <a href="[link]">[example tag text, corresponding to the id attribute]</a>
        Some body text
      </span>
    </div>
    ```
    """
    if tag.get("class", [])[0] != "EX":
        return False

    tag_id = tag.get("id")
    if not tag_id:
        return False

    reference_regex = re.compile(r"^((?:n\.|i\.)\d{1,2})")
    if not reference_regex.match(tag_id):
        return False

    # children: list[Tag] = tag.find_all("span", recursive=False)

    # if len(children) != 1 or not (
    #     children[0].name == "span"
    # ):
    #     return False

    # hyperlink = children[0].find("a")

    # if not hyperlink:
    #     return False

    # label = hyperlink.get_text()

    # reference_regex = re.compile(r"^(\[(?:i\.)?\d{1,2}\])")

    # if not reference_regex.match(label):
    #     return False

    return True


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

    # Remove elements added by editing.html
    for editor_tag in soup.find_all(id="editor"):
        # The editor tag wraps the document's text, so keep the contents of the tag and remove just the tag itself
        editor_tag.unwrap()

    for element in soup.select("button, label.switch, span.sider, input#editing"):
        element.decompose()

    return soup


def remove_badges(soup: BeautifulSoup):
    """
    Removes badge elements added to the HTML that are not necessary for the Docx.
    Badges are typically represented as images with specific classes or IDs.
    """
    # Example: Remove images with class 'badge' or id 'badge-container'
    for badge in soup.select(".inform, .norm"):
        text = badge.get_text()
        if not text.startswith("(") and not text.endswith(")"):
            text = "(" + text + ")"
        badge.insert_before(NavigableString(text))
        badge.decompose()

    return soup

def remove_citations(soup: BeautifulSoup):
    """
    Adjust citation elements to ensure they are properly formatted for Docx conversion.
    """
    citations = soup.find_all("span", class_="citation")

    for citation in citations:
        citation.unwrap()

    return soup

def compute_height_and_width_from_file(file_path: str):
    """
    Computes the height and width of images in the document based on the provided file.
    """
    # Read the file size
    if not os.path.isfile(file_path):
        return None

    if file_path.lower().endswith(".svg"):
        # For SVG files, we need to get the dimensions from the XML
        with open(file_path, "r") as f:
            svg_content = f.read()
            svg_tree = ET.ElementTree(ET.fromstring(svg_content))
            svg_root = svg_tree.getroot()

            width = svg_root.attrib.get("width")
            height = svg_root.attrib.get("height")

            if width is None or height is None:
                viewBox = svg_root.attrib.get("viewBox")
                if viewBox:
                    _, _, width, height = viewBox.split()
                    width = width.strip()
                    height = height.strip()

            if width and height:
                width = int(width.replace("px", ""))
                height = int(height.replace("px", ""))

    else:
        # Get the dimensions of the image
        with Image.open(file_path) as img:
            width, height = img.size
    # here we only set the bigger one, that way the other one scales accordingly with the form-factor
    if width > height:
        width = min(width, WORD_A4_MAX_WIDTH_PIXEL)
        height = None
    else:  # height > width
        height = min(height, WORD_A4_MAX_HEIGHT_PIXEL)
        width = None
    return (width, height)


def change_images_to_use_high_quality(soup: BeautifulSoup, src: str):
    """
    In the HTML, images are sourced from the PNG files. Change the file extension from `.png` to `.emf` to use the EMFs instead.

    Use a different file format if the EMF doesn't exist.

    #### File type priority:
    1. EMF
    2. SVG
    3. PDF
    4. PNG
    5. JPG
    """
    for img in soup.find_all("img"):
        img_src = img.get("src")
        width = img.get("width")
        height = img.get("height")
        img_name, img_format = os.path.splitext(img_src)
        img_name = img_name.split("/")[-1]
        img_size = None  # Initialize the image size
        original_name = img_name + img_format
        original_width = width
        original_height = height

        # Replace file type based on priority
        if os.path.isfile(f"{src}/media/{img_name}.emf"):
            img_src = img_src.replace(".png", ".emf")
            # For EMF files it is not required to look for their size
            # This is justified by the fact that we assume EMF files come out of a DOCX, where the user decided an initial size
            # The size decided by the user is preserved in the EMF file when we extract it

        elif os.path.isfile(f"{src}/media/{img_name}.svg"):
            img_src = img_src.replace(".png", ".svg")
            file_path = f"{src}/media/{img_name}.svg"
            img_size = compute_height_and_width_from_file(file_path)

        if os.path.isfile(f"{src}/media/{img_name}.pdf"):
            img_src = img_src.replace(".png", ".pdf")
            file_path = f"{src}/media/{img_name}.pdf"
            img_size = compute_height_and_width_from_file(file_path)

        elif os.path.isfile(f"{src}/media/{img_name}.png"):
            file_path = f"{src}/media/{img_name}.png"
            img_size = compute_height_and_width_from_file(file_path)

        # elif os.path.isfile(f"{src}/media/{img_name}.jpg"):
        #     img_src = img_src.replace(".png", ".jpg")

        img["src"] = img_src
        if width and not height:
            img["width"] = width
            img["height"] = None
        elif height and not width:
            img["height"] = height
            img["width"] = None
        elif width and height:
            img["width"] = width
            img["height"] = height
        elif img_size:
            if img_size[0] is not None:
                img["width"] = img_size[0]
            if img_size[1] is not None:
                img["height"] = img_size[1]
        
        img["alt"] = "alt:" + img["alt"] if img.get("alt") else ""
        img["alt"] += f"|name:{original_name}"
        if original_width:
            img["alt"] += f"|width:{original_width}"
        if original_height:
            img["alt"] += f"|height:{original_height}"

    return soup


def modify_links(soup: BeautifulSoup):
    """In preparation for merging all the HTMLs into a single document, remove references to different documents within internal links"""
    links = soup.find_all("a", href=True)

    href_regex = re.compile(r"(?:\d{1,2}-)?(.+?)\.html#(.+)")

    for link in links:
        match = href_regex.match(link["href"])
        if match:
            link["href"] = f"#{match.group(2)}"

    return soup


def handle_italic_monospace(soup: BeautifulSoup):
    """Handles spans that apply both the `HTML_Italic` and `HTML_Monospace` classes by converting them into a single custom tag that can be handled during postprocessing."""
    ems = soup.find_all("em")


    for em in ems:
        code = em.find("code", recursive=False)
        if code:
            text = code.get_text()
            new_text = NavigableString(f"{{{{{{HTML-Sample}}}}}}{text}{{{{{{/HTML-Sample}}}}}}")
            em.replace_with(new_text)

    return soup


def get_plaintext_from_codeblock(pre: Tag):
    """
    Return a list of the lines of text contained in a code block.

    The text is retrieved from the provided `<pre>` tag's `<code>` child tag, which it always has. Preserves indentation by replacing any tabs with tab placeholders, which is necessary because Pandoc trims preceding whitespace.
    """
    # There will only be one code tag inside the pre tag
    code = pre.find("code", recursive=False)
    if not code:
        return []  # Nothing to do here

    # Get the direct children of the code tag. Each span contains an <a> tag and a series of spans representing a single line's worth of text.
    code_children = code.find_all("span", recursive=False)

    # Keep track of each child's spans' text
    lines: list[str] = []

    for code_child in code_children:
        spans = code_child.find_all("span", recursive=False)
        line = ""

        for i, span in enumerate(spans):
            span_text = span.get_text()
            # Convert pairs of non-breaking spaces to TAB_PLACEHOLDER throughout the entire line
            # Code blocks have double the amount of non-breaking spaces as tabs that they should have
            new_span_text = span_text.replace("\xa0\xa0", TAB_PLACEHOLDER)
            # Keep remaining single \xa0 as-is to preserve spacing
            line = f"{line}{new_span_text}"

        lines.append(line)
        line = ""  # Prepare for next line

    return lines

def make_tag(text: str, classname: str, is_link=False):
    return f"{{{{{{{classname}}}}}}}{text}{{{{{{/{classname}}}}}}}"

def handle_examples_and_notes(soup: BeautifulSoup):
    """
    Unwrap the inner divs within examples and notes.
    - Examples are divs that apply the `EX` class with two child divs with no attributes
    - Notes are divs that apply the `NO` or `TAN` classes (one or the other)

    Performs the following tasks:
    1. Unwrap the inner divs to reduce the div's contents to the tag and its body content all at the same level
    2a. Conditional handling depending on the content type of the first body element
        1. If the content is another paragraph, simply merge it with the first paragraph (the label/tag)
        2. If the content is a code block, take the first line and merge it with the label/tag so the code block is level with the label tag, then add in all the other lines after it.
    2b. If applicable, handling of all subsequent body elements with a similar logic to the handling of the first element
    3. Wrap the contents of child elements, such as spans or paragraphs, that apply some style with tags containing that style name so the style can be readded during postprocessing.
    """

    def handle_first_element(soup: BeautifulSoup, children: list[Tag]):
        """Handles the first element in the example or note. It is handled differently than other elements because the first element interacts with the example/note tag, since the body text should be on-level with the tag."""

        def handle_paragraph(soup: BeautifulSoup, tag: Tag, body: Tag):
            """Simply consolidate the body paragraph with the tag paragraph"""
            tag_body_para = soup.new_tag("p")
            tag_body_para.append(tag.get_text())
            # tag_body_para.append(body.get_text())

            for child in body.children:
                tag_body_para.append(copy.copy(child))

            # Replace the two old paragraphs with the single new paragraph
            tag.insert_before(tag_body_para)
            tag.decompose()
            body.decompose()

            return soup

        def handle_code_block(soup: BeautifulSoup, tag: Tag, body: Tag):
            """Leave the code block as <pre><code> and let Pandoc handle it"""
            # Simply unwrap the body div but keep the pre/code structure intact
            # Move tag and body to the same level
            tag_para = tag
            body_div = body
            
            # Unwrap the body div to expose its contents (pre/code)
            for child in list(body_div.children):
                tag_para.insert_after(child)
            
            body_div.decompose()
            
            return soup

        # Existing tag and (first or only) body element
        tag = children[0]
        body = children[1]

        if body.name == "p":
            soup = handle_paragraph(soup, tag, body)

        if body.name == "div" and body.find("pre"):
            soup = handle_code_block(soup, tag, body)
        
        # Handle lists as first element - unwrap the div to expose the list
        if body.name == "div" and (body.find("ol") or body.find("ul")):
            body.unwrap()

        return soup

    def handle_subsequent_elements(soup: BeautifulSoup, body_elements: list[Tag]):
        """Ensure correct indentation of all other body elements"""

        def handle_codeblock(soup: BeautifulSoup, element: Tag):
            """
            Leave the code block as <pre><code> and let Pandoc handle it
            """
            pre = element.find("pre")
            if not pre:
                return soup  # Nothing to do here

            # Simply unwrap the element div to expose the pre/code
            element.unwrap()
            
            return soup
        
        def handle_list(soup: BeautifulSoup, element: Tag):
            """
            Unwrap div containers around lists to preserve list structure
            """
            # Simply unwrap the div to expose the list
            element.unwrap()
            return soup

        for element in body_elements:
            if element.name == "div" and element.find("pre"):
                handle_codeblock(soup, element)
            elif element.name == "div" and (element.find("ol") or element.find("ul")):
                handle_list(soup, element)

        return soup

    def wrap_child_elements_with_style_tags(
        soup: BeautifulSoup, ex_no_tan_children: list[Tag]
    ):
        """
        Wrap any child elements (spans, paragraphs, etc) with tags containing their styles. This is necessary because the entire example/note div will be flattened by Pandoc and the inner styles will be lost otherwise. Later, these tags will be used after conversion to Docx to restore the styles.

        #### Tag format

        {{{stylename}}}[tag contents]{{{/stylename}}}
        """

        for child in ex_no_tan_children:
            grandchildren: list[Tag] = list(child.find_all())

            for grandchild in grandchildren:
                grandchild_class = grandchild.get("class", [])

                # If the grandchild has no class, try to inherit from the nearest
                # ancestor between the grandchild and the current `child` that
                # defines a class (so nested tags inside a styled span inherit it).
                if not grandchild_class:
                    ancestor = grandchild.parent
                    while ancestor and ancestor is not child:
                        if ancestor.has_attr("class"):
                            anc_cls = ancestor.get("class", [])
                            if isinstance(anc_cls, str):
                                anc_cls = [anc_cls]
                            if anc_cls:
                                grandchild_class = anc_cls
                                break
                        ancestor = ancestor.parent

                # Skip sourceCode elements and anything inside pre/code blocks
                # (sourceCode is a paragraph style and can't be applied inside EX paragraph)
                if 'sourceCode' in grandchild_class:
                    continue
                if grandchild.find_parent(['pre', 'code']):
                    continue

                text = grandchild.get_text()

                # If the grandchild has a class (or inherited one), handle
                # class-based wrapping first so that nested formatting (e.g.
                # <strong>) inside a styled span is considered part of that
                # style. When nested basic-format tags exist, build a single
                # placeholder string with inner placeholders so the final
                # output is nested like {{{class}}}{{{strong}}}text{{{/strong}}}{{{/class}}}.
                if len(grandchild_class) > 0:
                    grandchild_class = grandchild_class[0]

                    # If nested tags exist, build an inner string where basic
                    # format tags are converted to their own placeholders, then
                    # wrap the whole result with the outer class placeholder.
                    if grandchild.find(True):
                        parts: list[str] = []
                        for node in list(grandchild.contents):
                            if isinstance(node, NavigableString):
                                parts.append(str(node))
                            elif isinstance(node, Tag):
                                # If the descendant is a basic format tag, create
                                # its own placeholder; otherwise, use its text.
                                if node.name in HTML_BASIC_FORMAT_TAGS:
                                    parts.append(make_tag(node.get_text(), node.name))
                                else:
                                    parts.append(node.get_text())

                        full_text = "".join(parts)
                        tagged_text = make_tag(full_text, grandchild_class)

                        grandchild.replace_with(NavigableString(tagged_text))
                        continue

                    # No nested tags: safe to replace whole element with placeholder
                    tagged_text = make_tag(text, grandchild_class)
                    grandchild.clear()
                    grandchild.append(tagged_text)
                    if grandchild.parent:
                        grandchild.unwrap()
                    continue

                if grandchild.name in HTML_BASIC_FORMAT_TAGS and not is_reference(
                    child.parent
                ):
                    tagged_text = make_tag(text, grandchild.name)

                    # If the grandchild contains nested tags (e.g. <span><strong>..</strong></span>),
                    # avoid clearing/unwrapping to preserve inner formatting. Instead only
                    # replace direct text children with the placeholder.
                    if grandchild.find(True):
                        for txt in list(grandchild.find_all(string=True, recursive=False)):
                            txt.replace_with(make_tag(str(txt), grandchild.name))
                        continue

                    grandchild.clear()
                    grandchild.append(tagged_text)
                    if grandchild.parent:  # Only unwrap if the element still has a parent (is part of the tree)
                        grandchild.unwrap()

                if (
                    grandchild.name == "a"
                    and grandchild.has_attr("href")
                    and not is_reference(child.parent)
                ):
                    tagged_text = make_tag(text, f'LINK|{grandchild.get("href")}')

                    # Preserve nested formatting inside links: only replace direct text nodes
                    if grandchild.find(True):
                        for txt in list(grandchild.find_all(string=True, recursive=False)):
                            txt.replace_with(make_tag(str(txt), f'LINK|{grandchild.get("href")}'))
                    else:
                        grandchild.clear()
                        grandchild.append(tagged_text)

                if len(grandchild_class) > 0:
                    grandchild_class = grandchild_class[
                        0
                    ]  # Get the class name at index 0, since there will always be only one class

                    tagged_text = make_tag(text, grandchild_class)

                    # If nested tags exist, replace only direct text children to preserve
                    # inner formatting; otherwise continue with clear+unwrap.
                    if grandchild.find(True):
                        # propagate the grandchild's class to all descendant tags so
                        # nested formatting inherits the style
                        for descendant in list(grandchild.find_all(True)):
                            existing = descendant.get("class", [])
                            if isinstance(existing, str):
                                existing = [existing]
                            if grandchild_class not in existing:
                                descendant["class"] = existing + [grandchild_class]

                        for txt in list(grandchild.find_all(string=True, recursive=False)):
                            txt.replace_with(make_tag(str(txt), grandchild_class))
                        # keep the span/div wrapper as it contains nested formatting
                    else:
                        grandchild.clear()
                        grandchild.append(tagged_text)
                        if grandchild.parent:
                            grandchild.unwrap()

        return soup

    divs = soup.find_all(
        "div", class_=lambda cls: cls in EXAMPLE_NOTE_CLASSES if cls else False
    )
    
    for div in divs:
        children: list[Tag] = div.find_all(recursive=False)

        if (
            len(children) != 2
            or not (children[0].name == "div" and children[1].name == "div")
            or not (len(children[0].attrs) == 0 and len(children[1].attrs) == 0)
        ):
            continue  # Not the correct structure of examples or notes

        # Step 1: Unwrap the divs
        for child in children:
            child.unwrap()

        # Step 2a: Combine the first and second children (the tag and the (first or only) body element)
        children: list[Tag] = div.find_all(
            recursive=False
        )  # Update children now that the divs were removed

        if not (len(children) >= 2):
            continue  # Not a correctly formatted example or note

        soup = handle_first_element(soup, children)

        if len(children) == 2:
            continue  # At this point, examples and notes with only one child are done

        # Step 2b
        soup = handle_subsequent_elements(soup, children[2:])

    # Step 3
    divs = soup.find_all(
        "div", class_=lambda cls: cls in EXAMPLE_NOTE_CLASSES if cls else False
    )  # Refresh list with changes

    for div in divs:
        children: list[Tag] = div.find_all(recursive=False)

        soup = wrap_child_elements_with_style_tags(soup, children)

    return soup


def handle_abbreviations(soup: BeautifulSoup):
    """
    Convert examples into a docx-friendly form, adding a tab placeholder to ensure correct indentation.

    #### Start
    `<div class="EX"><div>[abbreviation]</div><div>[meaning]</div></div>`

    #### End
    `<div class="EX">[abbreviation]{{{TAB}}}[meaning]</div>`
    """
    ABBREVIATION_CLASS = "EW"
    abbreviations = soup.find_all("div", attrs={"class": ABBREVIATION_CLASS})

    if len(abbreviations) == 0:
        return soup  # Nothing to do here

    for abbr in abbreviations:
        children = abbr.find_all("div")

        if len(children) != 2:
            continue  # Not an abbreviation

        tab = NavigableString(TAB_PLACEHOLDER)
        abbr_div = children[0]

        abbr_div.insert_after(tab)

        for child in children:
            child.unwrap()

    return soup


def convert_codeblock_styles_to_etsi(soup: BeautifulSoup):
    """Style codeblocks to use ETSI styles rather than the styling applied by the HTML codeblock"""
    pres = soup.find_all("pre")

    for pre in pres:
        lines: list[str] = get_plaintext_from_codeblock(pre)
        if len(lines) == 0:
            return soup  # Nothing to do here

        new_codeblock = soup.new_tag("div")

        for line in lines:
            line_para = soup.new_tag("p")

            # Create a suffix for this tag specifying whether space should be added after the paragraph. Only the last paragraph in the code block should have the space added.
            suffix = NO_SPACE
            if line == lines[-1]:
                suffix = WITH_SPACE

            # Convert \xa0 to &nbsp; to preserve non-breaking spaces
            preserved_line = line.replace("\xa0", "&nbsp;")
            
            # Use a span with white-space: pre to preserve formatting through Pandoc
            span = soup.new_tag("span", style="white-space: pre")
            span.append(NavigableString(
                f"{{{{{{HTML_Sample/{suffix}}}}}}}{preserved_line}{{{{{{/HTML_Sample/{suffix}}}}}}}"
            ))
            line_para.append(span)

            new_codeblock.append(line_para)

        pre.insert_before(new_codeblock)
        pre.decompose()

    return soup


def cleanup_code_tags(soup: BeautifulSoup):
    """Throughout the text, there are portions of text enclosed in `<` and `>`. Unwrap these code tags to preserve just the text. If the text is a hyperlink, replace the code tag with a hyperlink containing the link."""
    code_tags = soup.find_all("code")

    for code in code_tags:
        text = code.text

        if len(text) == 0 or (text[0] != "<" and text[-1] != ">"):
            continue

        is_link = "https://" in text[1:] or "http://" in text[1:]

        if is_link:
            text = text[1:-1]  # Remove < and >
            hyperlink = soup.new_tag("a", attrs={"href": text})
            hyperlink.append(text)

            code.replace_with(hyperlink)

        elif text == "<!-- -->":
            code.parent.decompose()

        else:
            plaintext = NavigableString(text)

            code.replace_with(plaintext)

    return soup

CSS_BIU = combine_biu_classes()
def create_custom_tags_for_bold_italic_underline_styles(soup: BeautifulSoup):
    """Some spans apply complex styles part of which involves bolding, italicizing, or underlining. Create custom tags with the class name"""
    
    # Classes that should be handled via custom-style in Lua filter, not via text replacement
    # EXCLUDE_CLASSES = {"HTML-Keyboard", "HTML-Definition"}

    spans = soup.find_all("span", class_=lambda cls: cls in CSS_BIU if cls else False)

    for span in spans:
        cls = span.get("class")[0]
        
        # Skip classes that should maintain their span structure for Lua filter processing
        # if cls in EXCLUDE_CLASSES:
        #     continue
            
        if cls in HANDLE_UNDERSCORE_CLASSES:
            # The styles for these classes do not have the underscores
            cls = cls.replace("_", " ")

        text = f"{{{{{{{cls}}}}}}}{span.get_text()}{{{{{{/{cls}}}}}}}"

        span.replace_with(NavigableString(text))

    return soup

def create_custom_tags_for_bold_italic_underline_tags(soup: BeautifulSoup):
    """Some tags apply basic formatting styles like bolding, italicizing, or underlining. Create custom tags with the tag name as the class to preserve the style through the conversion to docx, since these styles can sometimes be lost when nested inside other tags."""
    for tag_name in ["strong", "em", "u", "sup", "sub", "i", "b"]:
        tags = soup.find_all(tag_name)

        for tag in tags:
            text = f"{{{{{{{tag_name}}}}}}}{tag.get_text()}{{{{{{/{tag_name}}}}}}}"

            tag.replace_with(NavigableString(text))

    return soup


def prepare_table_cell_classes(soup: BeautifulSoup):
    """Transform table cells to prepare them for conversion to docx. Unwrap the div and apply the div's class to all the paragraphs contained therein."""
    for cell in soup.find_all(["th", "td"]):
        div = cell.find("div")

        if not div or not div.get("class")[0]:
            continue

        # Table notes already have their style applied to them, skip them here to avoid messing them up
        if div.find("div", class_="TAN"):
            continue

        div_class = div.get("class")[0]

        # Add a tag with the class to help apply the corresponding style during postprocessing
        label_para = soup.new_tag("p")
        label_para.append(NavigableString(f"{{{{{{{div_class}}}}}}}"))

        div.insert(0, label_para)

        # Ensure plaintext is wrapped in a paragraph so paragraph styles can be applied to it
        for child in div.children:
            try:
                if not isinstance(child, NavigableString):
                    continue

                para = soup.new_tag("p").append(child.get_text())
                child.replace_with(para)
            except ValueError:
                p_warning(
                    f"Could not add child: {repr(child)} to paragraph in table cell"
                )

        div.unwrap()

    return soup


def add_whitespace_placeholder_to_headings(soup: BeautifulSoup):
    """Adds placeholders for tabs and newline characters in headers that must be maintained in the Docx."""
    HEADER_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]
    headers = soup.find_all(HEADER_TAGS)

    main_headers = r"\d+(?:\.\d+){0,5}"
    annex_headers = r"Annex\s[A-Z](?:\s(?:\(normative\)|\(informative\)))?:"
    annex_subheaders = r"[A-Z](?:\.\d{1,5})+"

    tabbed_header_regex = rf"^({main_headers}|{annex_subheaders})\s"  # The headers that should have a tab offset
    newline_header_regex = rf"^({annex_headers})\s*"

    for header in headers:
        replacement_text = re.sub(
            tabbed_header_regex, rf"\1{TAB_PLACEHOLDER}", header.get_text().lstrip()
        )
        replacement_text = re.sub(
            newline_header_regex, rf"\1{NEWLINE_PLACEHOLDER}", replacement_text
        )

        if TAB_PLACEHOLDER in replacement_text:
            header.clear()
            header.append(NavigableString(replacement_text))

        if NEWLINE_PLACEHOLDER in replacement_text:
            header.clear()
            header.append(NavigableString(replacement_text))

    return soup

def prepend_links_with_invisible_text_tags(soup: BeautifulSoup, filename: str):
    """Prepend links with a InvisibleText tag containing the filename they are from to avoid duplicate link issues during consolidation"""
    links = soup.find_all("a", href=True, title=True)

    for link in links:
        tag = make_tag(link['title'], "InvisibleText")
        link.insert_before(NavigableString(tag))

    return soup

def add_invisible_text_for_external_links(soup: BeautifulSoup):
    """Add an InvisibleText tag containing the link's URL before external links to avoid duplicate link issues during consolidation"""
    spans = soup.find_all("span", class_="external-link")

    for span in spans:
        tag = make_tag("~", "InvisibleText")
        new_text = NavigableString(tag)
        span.insert_before(new_text)
        span.unwrap()  # Remove the original span, keeping its contents

    return soup

def add_invisible_text_for_remove_autonumbering(soup: BeautifulSoup):
    """Add an InvisibleText tag containing a tilde before elements that apply the remove-number class in order to get back an md that does not contain those numbers."""
    elements = soup.find_all(class_="remove-number")

    for element in elements:
        tag = make_tag("~~~", "InvisibleText")
        new_text = NavigableString(tag)
        element.insert_before(new_text)
        element.decompose()  # Remove the original element as it only serves to mark where autonumbering should be removed, which is handled during postprocessing

    return soup

def surround_blockquotes_with_invisible_text_tags(soup: BeautifulSoup):
    """Surround blockquotes with InvisibleText tags to preserve them during consolidation, since they can sometimes be mistakenly merged if they appear in multiple files"""
    blockquotes = soup.find_all("pre", class_=["text", "json"])

    for blockquote in blockquotes:
        start_text = ""
        end_text = ""

        if "json" in blockquote.get("class", []):
            start_text = "jsonStartBlockquote"
            end_text = "jsonEndBlockquote"
        elif "text" in blockquote.get("class", []):
            start_text = "textStartBlockquote"
            end_text = "textEndBlockquote"

        #insert as text nodes in the code element
        code = blockquote.find("code")
        if code:
            code.insert(0, start_text)
            code.append(end_text)
        else:
            blockquote.insert(0, start_text)
            blockquote.append(end_text)

    return soup

def surround_examples_and_notes_with_invisible_text_tags(soup: BeautifulSoup):
    """Surround examples and notes with InvisibleText tags to preserve them during consolidation, since they can sometimes be mistakenly merged if they appear in multiple files"""
    ex_no_tan_divs = soup.find_all(
        "div", class_=lambda cls: cls in ["EX", "NO", "TAN"] if cls else False
    )

    for div in ex_no_tan_divs:
        start_span = soup.new_tag("span", attrs={"class": "InvisibleText"})
        end_span = soup.new_tag("span", attrs={"class": "InvisibleText"})
        start_span.string = "startEXNO"
        end_span.string = "endEXNO"
        div.insert(0, start_span)
        div.append(end_span)

    return soup

def remove_diff_marks(soup: BeautifulSoup):
    """Removes the diff marks added to the HTML when the --diff or --diff-git flags are applied during conversion from Markdown to HTML."""
    # Remove del tags completely
    for delete in soup.find_all("del"):
        delete.decompose()
    # Remove the class row-added from the tr tags, and delete rows with the class row-removed
    for tr in soup.find_all("tr"):
        classes = tr.get("class", [])
        if "row-removed" in classes:
            tr.decompose()
        elif "row-added" in classes:
            new_classes = [cls for cls in classes if cls != "row-added"]
            if new_classes:
                tr["class"] = new_classes
            else:
                del tr["class"]
    # Remove ins tags by unwrapping their content
    for ins in soup.find_all("ins"):
        ins.unwrap()
    # Remove the class "diff-view-all" from all tags
    for tag in soup.find_all(
        class_=lambda cls: (
            cls in ["diff-view-all", "diff-changes-enable"] if cls else False
        )
    ):
        classes = tag.get("class", [])
        cleaned_classes = [
            cls
            for cls in classes
            if cls not in ["diff-view-all", "diff-changes-enable"]
        ]

        if cleaned_classes:
            tag["class"] = cleaned_classes
        else:
            # Remove class attribute if empty
            del tag["class"]

    return soup


# endregion


def fix_list_example_nesting(soup: BeautifulSoup):
    """
    Fix nesting issues when examples/notes appear between list elements.
    
    Pandoc tends to include divs that appear after </ol> as part of the last <li>,
    especially when the next element is <ol start="N">.
    
    We fix this by inserting a br separator after examples/notes that are
    followed by a list, forcing Pandoc to treat them as separate blocks.
    """
    examples_and_notes = soup.find_all(
        "div", class_=lambda cls: cls in EXAMPLE_NOTE_CLASSES if cls else False
    )
    
    for elem in examples_and_notes:
        next_sibling = elem.find_next_sibling()
        
        # Check if this example/note is followed by a list
        if next_sibling and next_sibling.name in ["ol", "ul"]:
            # Insert a br as separator to prevent nesting
            separator = soup.new_tag("br")
            elem.insert_after(separator)
    
    return soup

def fix_list_items_having_multiple_paragraphs(soup: BeautifulSoup):
    """
    Fix list items that have multiple paragraphs by merging the contents of all paragraphs into a single paragraph, since Pandoc tends to only keep the first paragraph in a list item and discard the rest.
    """
    list_items = soup.find_all("li")

    for li in list_items:
        paragraphs = li.find_all("p", recursive=False)

        if len(paragraphs) <= 1:
            continue  # Nothing to do here

        # Merge the contents of all paragraphs into the first one
        first_para = paragraphs[0]

        for para in paragraphs[1:]:
            for child in para.children:
                first_para.append(soup.new_string("\n"))  # Add a newline between paragraphs to preserve separation
                first_para.append(copy.copy(child))
            para.decompose()  # Remove the now-empty paragraph

    return soup


def preprocess(
    src: str, src_type: str, excluded_html_files: list[str], consolidated_html_path: str
):
    """
    ### Description
    Preprocessing mandatory for conversion from HTML to Docx. Performs the following tasks:
    1. Removes the table of contents Pandoc adds to the HTML.
    2. Sources images from their EMF files rather than from their PNG files.
    3. Removes file references from links.
    4. Formats examples and notes.
    5. Converts all remaining code blocks to the ETSI style.
    6. Cleans up the formatting of remaining code tags containing some plaintext enclosed in `< >`
    7. Converts Docx paragraph styles to Docx run styles in spans
    8. Consolidates the HTML files.

    ### Arguments
    - `src`: The source directory containing the HTML files to convert
    - `src_type`: The source file type, `html`
    - `excluded_html_files`: A list of HTML filenames that, should they occur within `src`, will not be included for conversion to Docx
    """

    for filename in os.listdir(src):
        if filename.endswith(src_type) and filename not in excluded_html_files:
            # Setup and preprocessing
            input_path = os.path.join(src, filename)
            with open(input_path, "r", encoding="utf-8") as html:
                soup = BeautifulSoup(html, "html.parser")
            soup = remove_diff_marks(soup)
            soup = remove_pandoc_toc(soup)
            soup = remove_badges(soup)
            soup = remove_citations(soup)
            soup = change_images_to_use_high_quality(soup, src)
            soup = modify_links(soup)
            soup = handle_italic_monospace(soup)
            soup = prepend_links_with_invisible_text_tags(soup, filename)
            soup = add_invisible_text_for_external_links(soup)
            soup = add_invisible_text_for_remove_autonumbering(soup)
            soup = handle_examples_and_notes(soup)
            soup = fix_list_example_nesting(soup)
            soup = fix_list_items_having_multiple_paragraphs(soup)
            soup = handle_abbreviations(soup)
            # soup = convert_codeblock_styles_to_etsi(soup)
            soup = cleanup_code_tags(soup)
            soup = create_custom_tags_for_bold_italic_underline_styles(soup)
            soup = create_custom_tags_for_bold_italic_underline_tags(soup)
            soup = prepare_table_cell_classes(soup)
            soup = add_whitespace_placeholder_to_headings(soup)
            soup = surround_blockquotes_with_invisible_text_tags(soup)
            soup = surround_examples_and_notes_with_invisible_text_tags(soup)

            contents = soup.decode_contents()

            new_filename = re.sub(
                "([\w-]+?).html", r"--preprocessed--\1.html", filename
            )  # Ensure file order is preserved by keeping the number in front
            output_path = os.path.join(src, new_filename)

            with open(output_path, "w", encoding="utf-8") as html_new:
                html_new.write(contents)

    handle_html_consolidation("create", src, consolidated_html_path)
