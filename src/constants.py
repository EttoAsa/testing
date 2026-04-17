from typing import Literal
from enum import IntEnum

# Parent directory for all generated files
FILEGEN_DIR = "GENERATED_FILES"

# Authorized filetypes for conversion to and conversion from
FRM_TYPE = Literal["html_dirty", "html", "md"]
TO_TYPE = Literal["html", "md", "docx"]

# CSS Source files that should maintain their current location and name
PERM_CSS_FILE = "ETSIstyles.css"
CSS_SRC = [PERM_CSS_FILE, "customCSS.css"]

# HTML Files to exclude from conversion when converting from HTML
TO_DOCX_EXCLUDED_HTML_FILES = ["index.html", "0--1.html", "front-page.html"]
TO_MD_EXCLUDED_HTML_FILES = ["index.html"]

# For HTML->Docx postprocessing
# These CSS classes have underscores, but correspond to styles the names of which have spaces where they would have underscores.
HANDLE_UNDERSCORE_CLASSES = [
    "HTML_Error",
    "HTML_Definition",
]

REFERENCE_MAPPING_MD_TO_HTML = "reference_mapping_md_to_html.json"


# Consolidated Markdown file and path
CONSOLIDATED_MD_NAME = "consolidated.md"

# Consolidated HTML file and path
CONSOLIDATED_HTML_NAME = "consolidated.html"

# Groups of related HTML tags
HEADER_TAGS = ["h1", "h2", "h3", "h4", "h5", "h6"]

# Class used for abbreviations. Used for making sure it isn't included among empty CSS classes (it is empty in the generated CSS, but not in styles.css)
ABBREVIATION_CLASS = "EW"

# Classes used for list items.
# Unordered lists: The number in the class name corresponds to its indentation level, with B1 and B1plus corresponding to top-level items and B5 corresponding to the most nested items.
LIST_HIERARCHY_CLASSES = [
    "B1",
    "B1plus",
    "B2",
    "B2plus",
    "B3",
    "B3plus",
    "B4",
    "B5",
]

# Ordered lists: `BL` for letters (ex., a., b.), `BN` for numbers (ex., 1., 2.)
ORDERED_LIST_ITEM_CLASSES = ["BL", "BN"]

# HTML tags that represent ordered and unordered lists
HTML_LIST_TAGS = ["ol", "ul"]

# Relative path to the reference doc used by Pandoc for formatting
REFERENCE_DOC = "customized_reference.docx"

# Output path for consolidated Docx
OUTPUT_DOC_NAME = "document.docx"

# Classes for examples and notes
EXAMPLE_NOTE_CLASSES = ["EX", "NO", "TAN"]
STYLES_FOR_EXAMPLES_NOTES = ["Source Code", "Compact"]

# HTML tags to look for nested in examples and notes - Pandoc doesn't handle these well, so they need to be handled
BOLD_TAGS = ["strong", "b"]
ITALIC_TAGS = ["em", "i"]
UNDERLINE_TAGS = ["u"]
STRIKETHROUGH_TAGS = ["del", "s"]
SUBSCRIPT_TAGS = ["sub"]
SUPERSCRIPT_TAGS = ["sup"]

HTML_BASIC_FORMAT_TAGS = [
    tag
    for group in [
        BOLD_TAGS,
        ITALIC_TAGS,
        UNDERLINE_TAGS,
        STRIKETHROUGH_TAGS,
        SUBSCRIPT_TAGS,
        SUPERSCRIPT_TAGS,
    ]
    for tag in group
]

# Suffixes for the style tags for individual lines
NO_SPACE = "NS"  # This paragraph shouldn't have any space after it
WITH_SPACE = "WS"  # Tis paragraph should have space after it

# Tab and newline placeholders to add during HTML-Docx preprocessing to ensure such characters are added during postprocessing
TAB_PLACEHOLDER = "{{{TAB}}}"
NEWLINE_PLACEHOLDER = "{{{NEWLINE}}}"


# MS Words works with 96dpi. Considering that 1 inch is 96 pixels, we can get the pixels from inches x 96.
# We have 5,08 cm of padding on top and on bottom, which is 2 inches. A4 pages are 11.69 inches tall.
# We have 5,08 cm of padding on left and right, which is 2 inches. A4 pages are 8.27 inches wide.
WORD_A4_MAX_HEIGHT_PIXEL = (
    800  # 9.69 inches x 96 = 928, we keep it safe and reduce it to 800
)
WORD_A4_MAX_WIDTH_PIXEL = (
    550  # 6.27 inches x 96 = 601, we keep it safe and reduce it to 550
)

MAX_HEADING_LEVEL = (
    6  # used in some features (such as auto-numbering) when processing documents
)


# region ETSI default files
# Files that precede user-defined files
FRONTPAGE = "front-page"
INT_PROP_RIGHTS = "intellectual-property-rights"
FOREWORD = "foreword"
MODAL_VERBS = "modal-verbs-terminology"
EXEC_SUM = "executive-summary"
INTRO = "introduction"
SCOPE = "clause-1_Scope"
REFS = "clause-2_References"
DEFS = "clause-3_Definitions"

# Files that follow user-defined files
ETSI_HISTORY = "history"

# Ordering
ETSI_INITIAL_FILES = [
    FRONTPAGE,
    INT_PROP_RIGHTS,
    FOREWORD,
    MODAL_VERBS,
    EXEC_SUM,
    INTRO,
    SCOPE,
    REFS,
    DEFS,
]

ETSI_FINAL_FILES = [ETSI_HISTORY]

NORMATIVE_REF_FILE = REFS
INFORMATIVE_REF_FILE = REFS
# endregion

# region Default Clause and Annex values
DEFAULT_CLAUSES = [f"clause-{i}" for i in range(4, 21)]
DEFAULT_HTML_CLAUSES = [f"clause-{i}" for i in range(1, 21)]

DEFAULT_ANNEXES = [f"annex-{letter}" for letter in "abcdefghijklmnopqrstuvwxyz"]
# endregion

# region Markdown Preprocessing Formatting Checks
METADATA_REGEX = r"(?:\{\.)?\w+(?:\s+\.\w+)*\}?"  # Follows the form `className` or `{.class1 .class2 ... .classN}`
DIV_START_REGEX = rf"[-\s]*:::\s{METADATA_REGEX}\s*"
DIV_END_REGEX = r"\s*:::\s*"

BAD_COLON_GROUP_REGEX = (
    r"(?<!:)(?::{1,2}|:{4,})(?!:)"  # Match all colon groups except the valid `:::`
)
# Match lines that start with : or :: and are not followed by letters
BAD_DIV_DELINEATOR_REGEX = r"^\s*(?::{1,2})(?![a-zA-Z])"
# endregion

TEXT_TO_REPLACE_IN_FRONTPAGE = [
    "WORKITEMNAME",
    "VERSION_NO",
    "DATE",
    "{{TYPEDOCUMENT}}",
    "{{TITLE}}",
    "{{PART}}",
    "{{SUBPART}}",
    "{{RELEASE}}",
    "{{WORKITEM}}",
    "{{KEYWORDS}}",
    "yyyy",
    "-mm",
]
GIT_STASH_NAME = "diff-check-stash"


class GIT_STASH_STATUSES(IntEnum):
    FAILED = 0
    NOTHING_TO_STASH = 1
    STASHED = 2
