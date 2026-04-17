import os
import sys
import re
from copy import deepcopy
import docx
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph
from random import randint

DEBUG = False  # print debug info switch


class CSS:
    def __init__(self, file_name, TESTING=False):
        self.file_name = file_name
        self.TESTING = TESTING
        self.para_styles = {}
        self.run_styles = {}

    def write(self):
        with open(self.file_name, "w") as f:
            f.write(
                "".join(
                    style.generate_css()
                    for style in {**self.para_styles, **self.run_styles}.values()
                )
                + ("" if self.TESTING else ".image_overlay {visibility: hidden;}")
            )

    def add_para_style(self, name, style):
        if name not in self.para_styles.keys():
            self.para_styles[name] = CSS_Style(name, style, self.TESTING)

    def add_run_style(self, name, style):
        if name not in self.run_styles.keys():
            self.run_styles[name] = CSS_Style(name, style, self.TESTING)

    def get_para(self, name):
        return self.para_styles[name]


class CSS_Style:
    """class that converts a word style in a css style"""

    def __init__(self, name, style, TESTING):
        self.class_name = name
        self.TESTING = TESTING
        # None values means we have to resolve Word style hierarchy
        self.text_align = None
        self.first_indent = None
        self.left_indent = None
        self.right_indent = None
        self.space_before = None
        self.space_after = None
        self.display = None
        self.gap = None
        self.align_items = None

        if hasattr(
            style, "font"
        ):  # this is a character style, a Paragraph style or an on_demand character style
            # font info
            self.font_name = self.inherit_property(style, "font.name")
            self.font_size = self.inherit_property(style, "font.size")
            self.bold = self.inherit_property(style, "font.bold")
            self.italic = self.inherit_property(style, "font.italic")
            self.underline = self.inherit_property(style, "font.underline")
            self.color = self.inherit_property(style, "font.color")
            self.is_char_style = isinstance(
                style, docx.styles.style.CharacterStyle
            ) and not isinstance(style, docx.styles.style.ParagraphStyle)

        else:  # this is an on_demand paragraph style
            self.font_name = None
            self.font_size = None
            self.bold = None
            self.italic = None
            self.underline = None
            self.color = None
            self.is_char_style = False

        if hasattr(
            style, "paragraph_format"
        ):  # this is a pragraph style or an on_demand paragraph style
            # paragraph format info
            self.text_align = self.inherit_property(style, "paragraph_format.alignment")
            # self.first_indent = self.inherit_property(style, 'paragraph_format.first_line_indent')
            # self.left_indent = self.inherit_property(style, 'paragraph_format.left_indent')
            # self.right_indent = self.inherit_property(style, 'paragraph_format.right_indent')
            self.first_indent = None
            self.left_indent = None
            self.right_indent = None
            self.space_before = self.inherit_property(
                style, "paragraph_format.space_before"
            )
            self.space_after = self.inherit_property(
                style, "paragraph_format.space_after"
            )

        # else: #this is a character style or an on_demand character style
        #     self.text_align = None
        #     self.first_indent = None
        #     self.left_indent = None
        #     self.right_indent = None
        #     self.space_before = None
        #     self.space_after = None

        # EXCEPTIONS
        if self.class_name == "NF":
            self.display = "flex"
            self.gap = Pt(4)
            self.align_items = "center"
        elif self.class_name == "FL":
            self.text_align = WD_ALIGN_PARAGRAPH.CENTER
            self.display = None
            self.gap = None
            self.align_items = None
        elif self.class_name == "TF":
            self.text_align = WD_ALIGN_PARAGRAPH.CENTER
            self.display = None
            self.gap = None
            self.align_items = None
        elif (
            self.class_name == "EX"
            or self.class_name == "NO"
            or self.class_name == "TAN"
        ):
            self.display = "flex"
            self.gap = Pt(12)
            self.left_indent = Pt(12)

    def inherit_property(self, style, property_path):
        """
        Helper method to inherit a property from the base style hierarchy.
        """
        current_style = style
        while True:
            property = current_style
            for attribute in property_path.split("."):
                property = getattr(property, attribute)

            if property is None:
                if getattr(current_style, "base_style", None):
                    current_style = current_style.base_style
                else:
                    break  # Exit the loop if there's no base_style
            else:
                break  # Exit if we found the property
        return property

    def generate_css(self):
        properties = ""

        # generate properties one-by-one

        # Use Monospace if Roboto Mono isn't supported by the browser
        if self.font_name:
            if self.font_name == "Roboto Mono":
                properties += f'font-family: "{self.font_name}", Monospace;\n\t'
            else:
                properties += f"font-family: {self.font_name};\n\t"

        if self.font_size:
            properties += f"font-size: {int(self.font_size.pt)}pt;\n\t"

        if self.bold:
            properties += f"font-weight: bold;\n\t"

        if self.italic:
            properties += f"font-style: italic;\n\t"

        if self.underline:
            properties += f"text-decoration: underline;\n\t"

        if self.color and self.color.rgb:
            if self.class_name.startswith("ondemand_"):
                if DEBUG:
                    print(self.class_name, self.color.rgb)
            properties += f"color: #{self.color.rgb};\n\t"

        if (
            self.text_align
        ):  # self.text_align is an enum and we use the name of the enum variable, but lower. e.g. WD_PARAGRAPH_ALIGNMENT.LEFT gives left
            properties += f"text-align: {self.text_align.name.lower()};\n\t"

        if self.first_indent:
            properties += f"text-indent: {self.first_indent.pt}pt;\n\t"

        if self.left_indent:
            properties += f"padding-left: {self.left_indent.pt}pt;\n\t"

        if self.right_indent:
            properties += f"padding-right: {self.right_indent.pt}pt;\n\t"

        if self.space_before:
            properties += f"margin-top: {self.space_before.pt}pt;\n\t"

        if self.space_after:
            properties += f"margin-bottom: {self.space_after.pt}pt;\n\t"

        if self.align_items:
            properties += f"align-items: {self.align_items};\n\t"

        if self.display:
            properties += f"display: {self.display};\n\t"

        if self.gap:
            properties += f"gap: {self.gap.pt}pt;\n\t"

        if self.TESTING:
            if self.class_name.startswith(
                "ondemand_"
            ):  # random color for ondemand styles
                # generates 3 different numbers between 0 and 240(with steps of 16 and shifted by 8)
                properties += "background-color: rgba({},{},{}, 0.5)".format(
                    randint(0, 15) * 16 + 8,
                    randint(0, 15) * 16 + 8,
                    randint(0, 15) * 16 + 8,
                )
            elif not (
                self.color and self.color.rgb
            ):  # adds a different background color to each different style, if they have no foreground color, to better visualize styles
                if self.is_char_style:
                    properties += "color: #{:02X}{:02X}{:02X}".format(
                        randint(0, 15) * 16 + 8,
                        randint(0, 15) * 16 + 8,
                        randint(0, 15) * 16 + 8,
                    )
                else:  # shade of gray for word extracted styles
                    gray = (128,) * 3
                    properties += "background-color: rgba({},{},{}, 0.5)".format(*gray)

        # put everything together
        css = f"""
                .{self.class_name} {{
                    {properties}
                }}

                """
        return css

    def __eq__(self, __o: object) -> bool:
        if type(__o) != type(self):
            return False
        return __o.class_name == self.class_name

    def __hash__(self) -> int:
        return hash(self.class_name)

    def __str__(self) -> str:
        return self.class_name + "\n" + self.generate_css() + "\n"


def get_name(str):
    """returns a css-friendly style name"""
    return "_".join(str.split(" ")).replace("+", "plus")


def diff_para_format(
    a: docx.text.parfmt.ParagraphFormat, b: docx.text.parfmt.ParagraphFormat
):
    """
    this method compares two paragraph formats and returns a list of string
    (the names of the properties that differs concatenated with the value of a's property)

    an empty list as a return means they have the same format
    """

    diffs = []

    if a == b:
        return diffs

    if a.alignment and a.alignment != b.alignment:
        diffs.append("alignment_" + a.alignment.name)

    if a.first_line_indent and a.first_line_indent != b.first_line_indent:
        diffs.append(
            "first_line_indent_" + str(int(a.first_line_indent.pt))
        )  # we take only th integer part because we can't have a . in the css class name

    if a.left_indent and a.left_indent != b.left_indent:
        diffs.append("left_indent_" + str(int(a.left_indent.pt)))

    if a.right_indent and a.right_indent != b.right_indent:
        diffs.append("right_indent_" + str(int(a.right_indent.pt)))

    if a.space_before and a.space_before != b.space_before:
        diffs.append("space_before_" + str(int(a.space_before.pt)))

    if a.space_after and a.space_after != b.space_after:
        diffs.append("space_after_" + str(int(a.space_after.pt)))

    return diffs


def diff_para_font(a: docx.text.run.Font, b: docx.text.run.Font):
    """
    this method compares two paragraph fonts and returns a list of string
    (the names of the properties that differs concatenated with the value of a's property)

    an empty list as a return means they have the same format
    """

    diffs = []
    if a == b:
        return diffs

    if a.name and a.name != b.name:
        diffs.append("name_" + a.name.replace(" ", "_"))

    if a.size and a.size != b.size:
        diffs.append("size_" + str(int(a.size.pt)))

    if a.color and a.color.rgb and a.color != b.color:
        diffs.append("color_" + str(a.color.rgb))

    # Check for bold, italic, and underline differences
    # Note: font properties can be True, False, or None (inherited from style)
    # We want to mark differences when the run explicitly has a format that differs from paragraph
    if a.bold is True and b.bold is not True:
        diffs.append("bold")
    
    if a.italic is True and b.italic is not True:
        diffs.append("italic")
    
    if a.underline is True and b.underline is not True:
        diffs.append("underline")

    return diffs


def mark_style(paragraphs):
    """adds styiling marks in paragraphs and runs"""
    for para in paragraphs:
        para_name = None
        if not para.style.builtin:
            # extract tag
            para_name = get_name(para.style.name)
            # convert style  in css
            api_css.add_para_style(para_name, para.style)
            background_highlight.add_para_style(para_name, para.style)
            # add style tag in text
            tag = f" [{{[--{para_name}--]}}]"
            if para.text[-len(tag) :] == tag:  # checks if the same tag alredy exists
                if DEBUG:
                    print("already marked with tag: ", tag)
            else:
                para.add_run(tag)

        else:
            if diffs := diff_para_format(
                para.paragraph_format, doc.styles["Normal"].paragraph_format
            ):  # ON DEMAND paragraph style
                para_name = "ondemand_PAR_" + "_".join(
                    diffs
                )  # concatenate everything with _
                # convert it to css
                api_css.add_para_style(para_name, para)
                background_highlight.add_para_style(para_name, para)

                tag = f" [{{[--{para_name}--]}}]"
                if (
                    para.text[-len(tag) :] == tag
                ):  # checks if the same tag alredy exists
                    if DEBUG:
                        print("already marked with tag: ", tag)
                else:
                    para.add_run(tag)

        for run in para.runs:
            if (
                run.text
            ):  # VERY IMPORTANT!! this skip images, without this they would get deleted
                run.text = run.text.replace(
                    "\t", "{{{{TAB}}}}"
                )  # mark tabs so that pandoic does not lose them
                if not run.style.name == "Default Paragraph Font":
                    # same as in para
                    run_name = get_name(run.style.name)
                    api_css.add_para_style(run_name, run.style)
                    background_highlight.add_para_style(run_name, run.style)
                    if f"@#! {run_name}" in run.text:
                        if DEBUG:
                            print("already marked with style: ", run_name)
                    else:
                        if run_name == "HTML_Sample":
                            run.text = run.text.replace(" ", "\xa0")
                        # add tag before and after each run(useful for lua script after pandoc parsing)
                        if f"@#! {run_name}" in run.text:
                            if DEBUG:
                                print("already marked with style: ", run_name)
                        else:
                            run.text = f"@#! {run_name} " + run.text + "@#!"
                            if run_name == "HTML_Error":
                                # Remove the run style because that apparently was blocking the creation of tags that apply the HTML_Error class
                                run.style = None
                else:  # if it has default characther style
                    if diffs := diff_para_font(
                        run.font, para.style.font
                    ):  # but different font from the para it is in, or it has default para style too
                        # create custom style ondemand for it
                        # if two runs uses the same font, they have the same name and thus the same style
                        # the name is the concatenation of differences found
                        run_name = "ondemand_CHAR_" + "_".join(diffs)
                        # instead of run.style, we use run as it has the font attrubute containig styling info for this particular run
                        api_css.add_para_style(run_name, run)
                        background_highlight.add_para_style(run_name, run)
                        if f"@#! {run_name}" in run.text:
                            if DEBUG:
                                print("already marked with style: ", run_name)
                        else:
                            run.text = f"@#! {run_name} " + run.text + "@#!"


def mark_table(tables):
    """recursevly adds marking styles to tables"""
    for table in tables:
        for row in table.rows:
            for cell in row.cells:
                mark_style(cell.paragraphs)
                mark_table(cell.tables)


def split_blockquote_runs_in_following_paragraph(paragraphs):
    """Move blockquote runs to a new paragraph when start marker is the second run."""
    marker_pairs = {
        "textStartBlockquote": "textEndBlockquote",
        "jsonStartBlockquote": "jsonEndBlockquote",
    }
    allowed_para_styles = {"EX", "NO"}

    def is_vanished(run):
        return run.font.hidden is True

    for para in paragraphs:
        if para.style.name not in allowed_para_styles:
            continue

        runs = list(para.runs)
        if len(runs) < 2:
            continue

        # First run stays in the original paragraph (e.g. "EXAMPLE 10:").
        start_idx = 1 if runs[1].text != "~~~" else 3

        if start_idx >= len(runs):
            continue

        start_run_text = runs[start_idx].text.strip() if runs[start_idx].text else ""
        if start_run_text not in marker_pairs or not is_vanished(runs[start_idx]):
            continue

        expected_end_marker = marker_pairs[start_run_text]
        end_idx = None
        for idx in range(start_idx + 1, len(runs)):
            run_text = runs[idx].text.strip() if runs[idx].text else ""
            if run_text == expected_end_marker and is_vanished(runs[idx]):
                end_idx = idx
                break

        if end_idx is None:
            continue

        runs_to_move = runs[start_idx + 1:end_idx]

        new_p = OxmlElement("w:p")
        para._p.addnext(new_p)
        new_para = Paragraph(new_p, para._parent)

        if para._p.pPr is not None:
            new_para._p.insert(0, deepcopy(para._p.pPr))

        try:
            new_para.style = "Source Code"
        except KeyError:
            if "SourceCode" in [s.name for s in para.part.document.styles]:
                new_para.style = "SourceCode"

        for run in runs_to_move:
            if run.text:
                new_para._p.append(run._r)

        if runs[start_idx].text and runs[end_idx].text:
            new_para.runs[0].text = runs[start_idx].text.lstrip() + new_para.runs[0].text
            new_para.runs[-1].text = new_para.runs[-1].text + runs[end_idx].text.rstrip()

        para._p.remove(runs[start_idx]._r)
        para._p.remove(runs[end_idx]._r)


def add_space_placeholders_in_blockquotes(paragraphs):
    """adds a space placeholder in empty paragraphs in blockquotes, to avoid them being lost during the HTML round-trip, since empty paragraphs are not rendered in HTML and thus get lost during the conversion back to DOCX"""
    for para in paragraphs:
        if "jsonStartBlockquote" in para.text and not (para.style.name == "Source Code" or para.style.name == "SourceCode"):
            print("Found blockquote start marker in paragraph with style ", para.style.name, " and text: ", para.text)
        if (para.style.name == "Source Code" or para.style.name == "SourceCode"):
            # replace spaces with {{{{SPACE}}}}
            for run in para.runs:
                run.text = run.text.replace(" ", "{{{{SPACE}}}}")

def show_vanished_elements(doc):
    """This method shows vanished links containing the original text from the markdown files, in order to replace it in the postprocessing with the links autogenerated"""
    for para in doc.paragraphs:
        for run in para.runs:
            if run.font.hidden and run.text and "~~~" not in run.text:
                run.font.hidden = False

def redefine_tags(paragraphs):
    for para in paragraphs:
        for run in para.runs:
            para_name = get_name(para.style.name)

def merge_examples_and_notes(paragraphs):
    """
    Merge EX/NO note-example fragments split across multiple paragraphs.

    Pattern supported:
    - first paragraph (EX/NO) contains an InvisibleText run with startEXNO
    - last paragraph (EX/NO) contains an InvisibleText run with endEXNO
    - all paragraphs in between are merged in order by appending their runs
    - marker paragraphs are removed from the document
    """
    start_marker = "startEXNO"
    end_marker = "endEXNO"
    allowed_styles = {"EX", "NO", "TAN"}

    def is_marker_paragraph(para, marker):
        """True when paragraph style is EX/NO and an InvisibleText run contains *marker*."""
        if para.style.name not in allowed_styles:
            return False

        for run in para.runs:
            if not run.text:
                continue
            if run.style and run.style.name == "InvisibleText" and marker in run.text:
                return True
        return False

    def remove_paragraph(para):
        element = para._element
        parent = element.getparent()
        if parent is not None:
            parent.remove(element)

    paras = list(paragraphs)
    i = 0
    while i < len(paras):
        start_para = paras[i]

        if not is_marker_paragraph(start_para, start_marker):
            i += 1
            continue

        end_idx = None
        for j in range(i + 1, len(paras)):
            if is_marker_paragraph(paras[j], end_marker):
                end_idx = j
                break

        if end_idx is None:
            i += 1
            continue

        end_para = paras[end_idx]
        inner_paragraphs = [paras[k] for k in range(i + 1, end_idx)]

        if inner_paragraphs:
            target_para = inner_paragraphs[0]
            for source_para in inner_paragraphs[1:]:
                for run in source_para.runs:
                    target_para._p.append(deepcopy(run._r))
                remove_paragraph(source_para)

        remove_paragraph(start_para)
        remove_paragraph(end_para)

        # Refresh view after XML edits and continue from the same index.
        paras = list(paragraphs)
        continue


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: preprocessing.py file.docx")
        sys.exit(1)

    docname = f"{sys.argv[1]}"

    doc = docx.Document(docname)

    docname = os.path.splitext(os.path.basename(docname))[0]

    # Prepare directory/directories for file creation
    FILEGEN_DIR = "GENERATED_FILES"
    DOC_PARENT_DIR = os.path.join(FILEGEN_DIR, docname)
    TEMP_DIR = os.path.join(DOC_PARENT_DIR, "temp")

    if not os.path.exists(FILEGEN_DIR):
        os.makedirs(FILEGEN_DIR)

    if not os.path.exists(DOC_PARENT_DIR):
        os.makedirs(DOC_PARENT_DIR)

    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR)

    api_css = CSS(os.path.join(DOC_PARENT_DIR, f"{docname}.css"))
    background_highlight = CSS(
        os.path.join(TEMP_DIR, "background_highlight.css"), TESTING=True
    )

    split_blockquote_runs_in_following_paragraph(doc.paragraphs)

    add_space_placeholders_in_blockquotes(doc.paragraphs)

    show_vanished_elements(doc)

    # mark tables style info
    mark_table(doc.tables)

    # mark paragraphs and runs style info
    mark_style(doc.paragraphs)

    # merge_examples_and_notes(doc.paragraphs)

    # TODO either remove it or complete it
    # redefine_tags(doc.paragraphs)

    # add some custom styles
    if api_css.para_styles.get("HTML_Code"):
        api_css.get_para("HTML_Code").font_size = Pt(8)

    if api_css.para_styles.get("HTML_Keyboard"):
        api_css.get_para("HTML_Keyboard").font_size = Pt(10)

    if api_css.para_styles.get("HTML_Sample"):
        api_css.get_para("HTML_Sample").font_size = Pt(8)

    if api_css.para_styles.get("HTML_Variable"):
        api_css.get_para("HTML_Variable").font_size = Pt(8)

    # save files
    api_css.write()
    background_highlight.write()
    doc.save(os.path.join(TEMP_DIR, "temp.docx"))
