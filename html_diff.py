#!/usr/bin/env python3
import sys
from pathlib import Path
from diff_match_patch import diff_match_patch
from bs4 import (
    BeautifulSoup,
    NavigableString,
    Tag,
    Comment,
    MarkupResemblesLocatorWarning,
)
import warnings
import html

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)


def clone_element(elem, soup):
    """
    Clones an element preserving whitespace and structure.
    Recursively copies without serializing/parsing to avoid entity issues.
    """
    if isinstance(elem, NavigableString):
        if isinstance(elem, Comment):
            return Comment(str(elem))
        # Create a new string in the target soup
        return soup.new_string(str(elem))

    # For Tag elements, create a new tag and recursively copy children
    if isinstance(elem, Tag):
        new_tag = soup.new_tag(elem.name)
        # Copy attributes
        for key, value in elem.attrs.items():
            new_tag[key] = value
        # Recursively copy children
        for child in elem.children:
            new_child = clone_element(child, soup)
            new_tag.append(new_child)
        return new_tag
    
    # Fallback to string representation
    return soup.new_string(str(elem))


def diff_text_content(old_text: str, new_text: str, soup):
    """Diffs two text strings and returns list of BeautifulSoup elements with track changes."""
    if not old_text and not new_text:
        return []

    dmp = diff_match_patch()
    dmp.Diff_Timeout = 0

    diffs = dmp.diff_main(old_text, new_text)
    dmp.diff_cleanupSemantic(diffs)

    result = []
    for op, text in diffs:
        if op == -1:  # Deletion
            del_tag = soup.new_tag("del")
            del_tag["class"] = ["diff-view-all"]
            del_tag.string = text
            result.append(del_tag)
        elif op == 1:  # Insertion
            ins_tag = soup.new_tag("ins")
            ins_tag["class"] = ["diff-view-all"]
            ins_tag.string = text
            result.append(ins_tag)
        else:  # No change
            result.append(soup.new_string(text))

    return result


def is_whitespace_only(elem):
    """Checks if an element contains only whitespace."""
    if isinstance(elem, NavigableString) and not isinstance(elem, Comment):
        return not str(elem).strip()
    return False


def is_inside_source_code(elem):
    """Checks if an element is inside a sourceCode context."""
    if not isinstance(elem, Tag):
        # For NavigableString, check the parent
        if hasattr(elem, "parent") and elem.parent:
            return is_inside_source_code(elem.parent)
        return False

    # Check current element
    if "sourceCode" in elem.get("class", []):
        return True

    # Check parents
    parent = elem.parent
    while parent:
        if isinstance(parent, Tag) and "sourceCode" in parent.get("class", []):
            return True
        parent = parent.parent

    return False


def get_significant_children(elem):
    """Returns only significant children (not whitespace-only or comments).
    However, preserves all whitespace inside elements with class 'sourceCode'."""
    if not isinstance(elem, Tag):
        return []

    # Check if this element has class 'sourceCode' or is inside one
    is_source_code = is_inside_source_code(elem)

    if is_source_code:
        # Preserve all children including whitespace
        return [child for child in elem.children if not isinstance(child, Comment)]

    # Normal behavior: filter out whitespace-only elements
    return [
        child
        for child in elem.children
        if not (isinstance(child, Comment) or is_whitespace_only(child))
    ]


def remove_empty_track_changes(soup):
    """Removes all empty <del> and <ins> tags or those containing only whitespace."""
    for tag_name in ["del", "ins"]:
        for tag in soup.find_all(tag_name):
            # Check if the tag contains non-textual elements like img
            has_non_text_content = tag.find(
                ["img", "video", "audio", "iframe", "svg", "canvas"]
            )
            if has_non_text_content:
                continue

            # Check if the tag is empty or contains only whitespace
            text_content = tag.get_text().strip()
            if not text_content:
                tag.decompose()


def flatten_nested_track_changes(soup):
    """Removes nested <del> or <ins> tags of the same type, keeping only the outer one."""
    for tag_name in ["del", "ins"]:
        # Continue as long as there are nested tags to flatten
        changed = True
        while changed:
            changed = False
            for parent_tag in soup.find_all(tag_name):
                # Find all direct children of the same type
                direct_children = [
                    child
                    for child in parent_tag.children
                    if isinstance(child, Tag) and child.name == tag_name
                ]

                for child_tag in direct_children:
                    # Move the child's content to the parent and remove the child
                    child_contents = list(child_tag.children)
                    for content in child_contents:
                        child_tag.insert_before(content)
                    child_tag.decompose()
                    changed = True


def consolidate_adjacent_track_changes(soup):
    """
    Consolidates adjacent <del> or <ins> tags at the same level,
    maintaining the internal HTML structure.
    """
    for tag_name in ["del", "ins"]:
        changed = True
        while changed:
            changed = False
            # Find all tags of the specified type
            for tag in soup.find_all(tag_name):
                # Look for the next significant sibling (not whitespace)
                next_sibling = tag.next_sibling
                while (
                    next_sibling
                    and isinstance(next_sibling, NavigableString)
                    and not str(next_sibling).strip()
                ):
                    next_sibling = next_sibling.next_sibling

                # If the next sibling is of the same type, consolidate them
                if (
                    next_sibling
                    and isinstance(next_sibling, Tag)
                    and next_sibling.name == tag_name
                ):
                    # Move all the sibling's content to the current tag
                    sibling_contents = list(next_sibling.children)
                    for content in sibling_contents:
                        tag.append(content)

                    # Remove the now-empty sibling
                    next_sibling.decompose()
                    changed = True
                    break  # Restart from the first tag to avoid iteration issues


def get_table_structure(table_elem):
    """
    Extracts the structure of a table with rowspan/colspan.
    Returns a tuple representing the structure for comparison.
    """
    if not isinstance(table_elem, Tag) or table_elem.name != "table":
        return None

    structure = []

    # Get all rows
    rows = table_elem.find_all("tr")
    structure.append(("rows", len(rows)))

    # For each row, get cell structure
    for row in rows:
        cells = row.find_all(["td", "th"])
        row_structure = []
        for cell in cells:
            cell_info = (cell.name, cell.get("rowspan", "1"), cell.get("colspan", "1"))
            row_structure.append(cell_info)
        structure.append(tuple(row_structure))

    return tuple(structure)


def has_same_table_structure(old_table, new_table):
    """
    Checks if two tables have the same structure (same number of rows and same rowspan/colspan layout).
    """
    if not isinstance(old_table, Tag) or not isinstance(new_table, Tag):
        return False

    if old_table.name != "table" or new_table.name != "table":
        return False

    old_structure = get_table_structure(old_table)
    new_structure = get_table_structure(new_table)

    return old_structure == new_structure


def should_skip_recursive_diff(old_elem, new_elem):
    """
    Checks if an element should be treated as a single block
    instead of doing a recursive diff of its content.
    Now takes both old and new elements to check if they have the same structure.
    """
    if not isinstance(old_elem, Tag) or not isinstance(new_elem, Tag):
        return False

    # For table cells (td/th), check if they have rowspan or colspan
    if old_elem.name in ["td", "th"] and new_elem.name in ["td", "th"]:
        old_has_span = "rowspan" in old_elem.attrs or "colspan" in old_elem.attrs
        new_has_span = "rowspan" in new_elem.attrs or "colspan" in new_elem.attrs

        # Skip recursive diff only if spans are different
        if old_has_span or new_has_span:
            # Check if both have the same span attributes
            if old_has_span and new_has_span:
                old_rowspan = old_elem.get("rowspan", "1")
                new_rowspan = new_elem.get("rowspan", "1")
                old_colspan = old_elem.get("colspan", "1")
                new_colspan = new_elem.get("colspan", "1")

                # If spans are the same, allow recursive diff
                if old_rowspan == new_rowspan and old_colspan == new_colspan:
                    return False

            # Spans are different, treat as block
            return True

    # For tables, check if they have the same structure
    if old_elem.name == "table" and new_elem.name == "table":
        old_has_span = old_elem.find(
            lambda tag: tag.name in ["td", "th"]
            and ("rowspan" in tag.attrs or "colspan" in tag.attrs)
        )
        new_has_span = new_elem.find(
            lambda tag: tag.name in ["td", "th"]
            and ("rowspan" in tag.attrs or "colspan" in tag.attrs)
        )

        # If neither has spans, use simple table logic (don't skip)
        if not old_has_span and not new_has_span:
            return False

        # If both have spans, check if structure is the same
        if old_has_span and new_has_span:
            if has_same_table_structure(old_elem, new_elem):
                # Same structure, allow recursive diff (don't skip)
                return False

        # Different structure, treat as block
        return True

    return False


def has_different_image_src(old_elem, new_elem):
    """
    Checks if two img elements have different src attributes.
    """
    if not isinstance(old_elem, Tag) or not isinstance(new_elem, Tag):
        return False

    if old_elem.name == "img" and new_elem.name == "img":
        old_src = old_elem.get("src", "")
        new_src = new_elem.get("src", "")
        return old_src != new_src

    return False


def get_row_signature(row):
    """
    Creates a signature for a table row based on its content.
    Used to identify identical or similar rows.
    """
    if not isinstance(row, Tag) or row.name != "tr":
        return ""
    
    cells = row.find_all(["td", "th"])
    texts = [cell.get_text().strip() for cell in cells]
    return "|".join(texts)


def is_simple_table(table_elem):
    """
    Checks if a table is 'simple' (without rowspan/colspan).
    """
    if not isinstance(table_elem, Tag) or table_elem.name != "table":
        return False
    
    has_span = table_elem.find(
        lambda tag: tag.name in ["td", "th"]
        and ("rowspan" in tag.attrs or "colspan" in tag.attrs)
    )
    return has_span is None


def diff_table_rows(old_rows, new_rows, parent_result, soup):
    """
    Compares table rows and adds appropriate classes:
    - row-added for new rows
    - row-removed for deleted rows
    - modifies cells for changed rows
    """
    from difflib import SequenceMatcher

    # Create signature for each row
    old_sigs = [get_row_signature(row) for row in old_rows]
    new_sigs = [get_row_signature(row) for row in new_rows]

    # Use SequenceMatcher to find matches
    matcher = SequenceMatcher(None, old_sigs, new_sigs)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Identical rows - simply copy
            for i, j in zip(range(i1, i2), range(j1, j2)):
                new_copy = clone_element(new_rows[j], soup)
                parent_result.append(new_copy)

        elif tag == "replace":
            # Replaced rows - compare cell by cell
            for i, j in zip(range(i1, i2), range(j1, j2)):
                old_row = old_rows[i]
                new_row = new_rows[j]

                # Create a new result row
                result_row = soup.new_tag("tr")

                # Copy attributes from the new row
                for key, value in new_row.attrs.items():
                    result_row[key] = value

                # Get cells from both rows
                old_cells = old_row.find_all(["td", "th"])
                new_cells = new_row.find_all(["td", "th"])

                # Compare cell by cell
                max_cells = max(len(old_cells), len(new_cells))
                for k in range(max_cells):
                    old_cell = old_cells[k] if k < len(old_cells) else None
                    new_cell = new_cells[k] if k < len(new_cells) else None

                    if old_cell is None and new_cell is not None:
                        # Added cell
                        result_cell = soup.new_tag(new_cell.name)
                        for key, value in new_cell.attrs.items():
                            result_cell[key] = value
                        # Copy the content inside an ins tag
                        for child in new_cell.children:
                            if isinstance(child, NavigableString):
                                ins = soup.new_tag("ins")
                                ins["class"] = ["diff-view-all"]
                                ins.string = str(child)
                                result_cell.append(ins)
                            else:
                                child_copy = clone_element(child, soup)
                                ins = soup.new_tag("ins")
                                ins["class"] = ["diff-view-all"]
                                ins.append(child_copy)
                                result_cell.append(ins)
                        result_row.append(result_cell)

                    elif new_cell is None and old_cell is not None:
                        # Removed cell
                        result_cell = soup.new_tag(old_cell.name)
                        for key, value in old_cell.attrs.items():
                            result_cell[key] = value
                        # Copy the content inside a del tag
                        for child in old_cell.children:
                            if isinstance(child, NavigableString):
                                delete = soup.new_tag("del")
                                delete["class"] = ["diff-view-all"]
                                delete.string = str(child)
                                result_cell.append(delete)
                            else:
                                child_copy = clone_element(child, soup)
                                delete = soup.new_tag("del")
                                delete["class"] = ["diff-view-all"]
                                delete.append(child_copy)
                                result_cell.append(delete)
                        result_row.append(result_cell)

                    else:
                        # Both cells exist - compare the content
                        result_cell = soup.new_tag(new_cell.name)
                        for key, value in new_cell.attrs.items():
                            result_cell[key] = value

                        # Recursively compare the cells' contents
                        old_cell_children = get_significant_children(old_cell)
                        new_cell_children = get_significant_children(new_cell)

                        for old_c, new_c in zip(old_cell_children, new_cell_children):
                            diff_elements(old_c, new_c, result_cell, soup)

                        # Handle extra children
                        if len(old_cell_children) > len(new_cell_children):
                            for old_c in old_cell_children[len(new_cell_children):]:
                                diff_elements(old_c, None, result_cell, soup)
                        elif len(new_cell_children) > len(old_cell_children):
                            for new_c in new_cell_children[len(old_cell_children):]:
                                diff_elements(None, new_c, result_cell, soup)

                        result_row.append(result_cell)

                parent_result.append(result_row)

            # Handle extra rows in case of different lengths
            if (i2 - i1) > (j2 - j1):
                # More old rows than new ones - extras are removed
                for i in range(i1 + (j2 - j1), i2):
                    old_row_copy = clone_element(old_rows[i], soup)
                    # Add row-removed class
                    if "class" in old_row_copy.attrs:
                        old_row_copy["class"].append("row-removed")
                    else:
                        old_row_copy["class"] = ["row-removed"]
                    old_row_copy["class"].append("diff-view-all")
                    parent_result.append(old_row_copy)

            elif (j2 - j1) > (i2 - i1):
                # More new rows than old ones - extras are added
                for j in range(j1 + (i2 - i1), j2):
                    new_row_copy = clone_element(new_rows[j], soup)
                    # Add row-added class
                    if "class" in new_row_copy.attrs:
                        new_row_copy["class"].append("row-added")
                    else:
                        new_row_copy["class"] = ["row-added"]
                    new_row_copy["class"].append("diff-view-all")
                    parent_result.append(new_row_copy)

        elif tag == "delete":
            # Removed rows
            for i in range(i1, i2):
                old_row_copy = clone_element(old_rows[i], soup)
                # Add row-removed class
                if "class" in old_row_copy.attrs:
                    old_row_copy["class"].append("row-removed")
                else:
                    old_row_copy["class"] = ["row-removed"]
                old_row_copy["class"].append("diff-view-all")
                parent_result.append(old_row_copy)

        elif tag == "insert":
            # Added rows
            for j in range(j1, j2):
                new_row_copy = clone_element(new_rows[j], soup)
                # Add row-added class
                if "class" in new_row_copy.attrs:
                    new_row_copy["class"].append("row-added")
                else:
                    new_row_copy["class"] = ["row-added"]
                new_row_copy["class"].append("diff-view-all")
                parent_result.append(new_row_copy)


def diff_elements(old_elem, new_elem, parent_result, soup):
    """
    Recursively compares two DOM elements and adds results to the parent.
    Properly handles tables and other structural elements.
    """
    # If one is None, handle insertion/deletion
    if old_elem is None and new_elem is not None:
        # Skip if it's only whitespace or a comment
        if is_whitespace_only(new_elem) or isinstance(new_elem, Comment):
            return

        if isinstance(new_elem, NavigableString):
            ins = soup.new_tag("ins")
            ins["class"] = ["diff-view-all"]
            ins.string = str(new_elem)
            parent_result.append(ins)
        else:
            new_copy = clone_element(new_elem, soup)
            ins = soup.new_tag("ins")
            ins["class"] = ["diff-view-all"]
            ins.append(new_copy)
            parent_result.append(ins)
        return

    if new_elem is None and old_elem is not None:
        # Skip if it's only whitespace or a comment
        if is_whitespace_only(old_elem) or isinstance(old_elem, Comment):
            return

        if isinstance(old_elem, NavigableString):
            delete = soup.new_tag("del")
            delete["class"] = ["diff-view-all"]
            delete.string = str(old_elem)
            parent_result.append(delete)
        else:
            old_copy = clone_element(old_elem, soup)
            delete = soup.new_tag("del")
            delete["class"] = ["diff-view-all"]
            delete.append(old_copy)
            parent_result.append(delete)
        return

    # Both are NavigableString: diff the text
    if isinstance(old_elem, NavigableString) and isinstance(new_elem, NavigableString):
        if isinstance(old_elem, Comment) or isinstance(new_elem, Comment):
            # Ignore comments
            return

        old_text = str(old_elem)
        new_text = str(new_elem)

        # Skip if both are empty
        if not old_text and not new_text:
            return

        # Check if we're inside sourceCode context
        in_source_code = is_inside_source_code(old_elem) or is_inside_source_code(
            new_elem
        )

        # If inside sourceCode and texts are identical, preserve whitespace with non-breaking spaces
        if in_source_code and old_text == new_text:
            # Replace spaces with non-breaking spaces to preserve them
            preserved_text = old_text.replace(" ", "\u00a0")  # Non-breaking space
            parent_result.append(soup.new_string(preserved_text))
            return

        diff_elements_list = diff_text_content(old_text, new_text, soup)
        if diff_elements_list:
            for elem in diff_elements_list:
                if isinstance(elem, NavigableString):
                    text = str(elem)
                    # If inside sourceCode, preserve spaces with non-breaking spaces
                    if in_source_code:
                        text = text.replace(" ", "\u00a0")
                    parent_result.append(soup.new_string(text))
                else:
                    # elem is already a proper BeautifulSoup tag
                    if elem.string and in_source_code:
                        # If inside sourceCode, preserve spaces with non-breaking spaces
                        text = elem.string.replace(" ", "\u00a0")
                        elem.string = text
                    parent_result.append(elem)
        return

    # One is a tag, the other is a string: they are different
    if type(old_elem) != type(new_elem):
        # Treat as deletion + insertion
        diff_elements(old_elem, None, parent_result, soup)
        diff_elements(None, new_elem, parent_result, soup)
        return

    # Both are Tags
    if isinstance(old_elem, Tag) and isinstance(new_elem, Tag):
        # If tags are different, treat as deletion + insertion
        if old_elem.name != new_elem.name:
            diff_elements(old_elem, None, parent_result, soup)
            diff_elements(None, new_elem, parent_result, soup)
            return

        # Special handling for images with different src
        if has_different_image_src(old_elem, new_elem):
            # Show both images: old in <del> and new in <ins>
            old_copy = clone_element(old_elem, soup)
            delete = soup.new_tag("del")
            delete["class"] = ["diff-view-all"]
            delete.append(old_copy)
            parent_result.append(delete)

            new_copy = clone_element(new_elem, soup)
            ins = soup.new_tag("ins")
            ins["class"] = ["diff-view-all"]
            ins.append(new_copy)
            parent_result.append(ins)
            return

        # Special handling for simple tables (table, tbody, thead, tfoot)
        if old_elem.name in ["table", "tbody", "thead", "tfoot"] and new_elem.name == old_elem.name:
            # For table, verify it's simple OR has the same structure
            if old_elem.name == "table":
                is_old_simple = is_simple_table(old_elem)
                is_new_simple = is_simple_table(new_elem)
                has_same_structure = has_same_table_structure(old_elem, new_elem)

                if (not is_old_simple or not is_new_simple) and not has_same_structure:
                    # Complex table with different structure, use normal method (will be caught by should_skip_recursive_diff)
                    pass
                else:
                    # Simple table OR complex table with same structure - handle with diff_table_rows
                    result_tag = soup.new_tag(old_elem.name)
                    for key, value in new_elem.attrs.items():
                        result_tag[key] = value

                    # Process children (tbody, thead, etc.)
                    old_children = get_significant_children(old_elem)
                    new_children = get_significant_children(new_elem)

                    # If there are tbody/thead/tfoot, process them recursively
                    # Otherwise, look for rows directly
                    has_sections = any(child.name in ["tbody", "thead", "tfoot"] for child in old_children if isinstance(child, Tag))
                    has_sections = has_sections or any(child.name in ["tbody", "thead", "tfoot"] for child in new_children if isinstance(child, Tag))

                    if has_sections:
                        # Process sections normally, they will handle their rows
                        matches = find_matching_elements(old_children, new_children)
                        for old_idx, new_idx in matches:
                            old_child = old_children[old_idx] if old_idx is not None else None
                            new_child = new_children[new_idx] if new_idx is not None else None
                            diff_elements(old_child, new_child, result_tag, soup)
                    else:
                        # No sections, rows are direct children of table
                        old_rows = [child for child in old_children if isinstance(child, Tag) and child.name == "tr"]
                        new_rows = [child for child in new_children if isinstance(child, Tag) and child.name == "tr"]
                        diff_table_rows(old_rows, new_rows, result_tag, soup)

                    parent_result.append(result_tag)
                    return

            # For tbody, thead, tfoot - always handle rows
            elif old_elem.name in ["tbody", "thead", "tfoot"]:
                result_tag = soup.new_tag(old_elem.name)
                for key, value in new_elem.attrs.items():
                    result_tag[key] = value

                old_children = get_significant_children(old_elem)
                new_children = get_significant_children(new_elem)

                old_rows = [child for child in old_children if isinstance(child, Tag) and child.name == "tr"]
                new_rows = [child for child in new_children if isinstance(child, Tag) and child.name == "tr"]

                diff_table_rows(old_rows, new_rows, result_tag, soup)
                parent_result.append(result_tag)
                return

        # Check if we should treat this element as a single block
        if should_skip_recursive_diff(old_elem, new_elem):
            # If they're identical, copy the new one
            if str(old_elem) == str(new_elem):
                new_copy = clone_element(new_elem, soup)
                parent_result.append(new_copy)
            else:
                # Otherwise, show as deletion + insertion
                diff_elements(old_elem, None, parent_result, soup)
                diff_elements(None, new_elem, parent_result, soup)
            return

        # Same tag: create the tag and compare contents
        result_tag = soup.new_tag(old_elem.name)

        # Copy attributes (prefer new ones if different)
        for key, value in new_elem.attrs.items():
            result_tag[key] = value

        # Compare only significant children using the matching algorithm
        old_children = get_significant_children(old_elem)
        new_children = get_significant_children(new_elem)

        # Find optimal matches
        matches = find_matching_elements(old_children, new_children)

        # Process matches in correct order
        for old_idx, new_idx in matches:
            old_child = old_children[old_idx] if old_idx is not None else None
            new_child = new_children[new_idx] if new_idx is not None else None
            diff_elements(old_child, new_child, result_tag, soup)

        parent_result.append(result_tag)


def find_matching_elements(old_children, new_children):
    """
    Finds optimal matching between old and new elements using an LCS approach.
    Returns a list of tuples (old_index|None, new_index|None).
    """
    from difflib import SequenceMatcher

    # Create string representations of elements for comparison
    old_reprs = [get_element_repr(child) for child in old_children]
    new_reprs = [get_element_repr(child) for child in new_children]

    # Use SequenceMatcher to find matches
    matcher = SequenceMatcher(None, old_reprs, new_reprs)

    operations = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Matching elements
            for i, j in zip(range(i1, i2), range(j1, j2)):
                operations.append((i, j))
        elif tag == "replace":
            # Replaced elements
            for i, j in zip(range(i1, i2), range(j1, j2)):
                operations.append((i, j))
            # If lengths are different, add operations for extra elements
            if (i2 - i1) > (j2 - j1):
                for i in range(i1 + (j2 - j1), i2):
                    operations.append((i, None))
            elif (j2 - j1) > (i2 - i1):
                for j in range(j1 + (i2 - i1), j2):
                    operations.append((None, j))
        elif tag == "delete":
            # Deleted elements
            for i in range(i1, i2):
                operations.append((i, None))
        elif tag == "insert":
            # Inserted elements
            for j in range(j1, j2):
                operations.append((None, j))

    return operations


def get_element_repr(elem):
    """
    Creates a compact representation of the element for comparison.
    Ignores the data-commit attribute in comparison.
    """
    if isinstance(elem, NavigableString):
        text = str(elem).strip()
        return f"TEXT:{text[:50]}" if text else "TEXT:"
    elif isinstance(elem, Tag):
        # Use tag name + key attributes (excluding data-commit) + beginning of content
        attrs_items = [
            (k, v) for k, v in sorted(elem.attrs.items()) if k != "data-commit"
        ]
        attrs_str = " ".join(f"{k}={v}" for k, v in attrs_items[:3])
        text = elem.get_text()[:50].strip()
        return f"TAG:{elem.name} {attrs_str} {text}"
    return "UNKNOWN"


def make_trackchanges_diff(
    old_path: str, new_path: str, out_path: str = "diff.html"
) -> int | None:
    try:    
        old_html = Path(old_path).read_text(encoding="utf-8")
    except Exception as e:
        old_html = "<html><body><div id='editor'></div></body></html>"

    try:
        new_html = Path(new_path).read_text(encoding="utf-8")
    except Exception as e:
        new_html = "<html><body><div id='editor'></div></body></html>"

    # Parse with BeautifulSoup
    old_soup = BeautifulSoup(old_html, "html.parser")
    new_soup = BeautifulSoup(new_html, "html.parser")

    # Find the div with id="editor" in both documents
    old_editor_div = old_soup.find("div", id="editor")
    new_editor_div = new_soup.find("div", id="editor")

    if not old_editor_div or not new_editor_div:
        print(
            "Error: unable to find div with id='editor' in one or both documents"
        )
        print(f"old_editor_div found: {old_editor_div is not None}")
        print(f"new_editor_div found: {new_editor_div is not None}")
        return None

    # Use the new document as base
    is_new_missing = new_html == "<html><body><div id='editor'></div></body></html>"
    result_soup = BeautifulSoup(old_html if is_new_missing else new_html, "html.parser")

    # Create a new div for the diff
    diff_div = result_soup.new_tag("div", id="editor")

    # Copy attributes from the original div (if there are any besides id)
    for key, value in new_editor_div.attrs.items():
        if key != "id":  # We've already set the id
            diff_div[key] = value

    # Recursively compare the content of the two divs using the matching algorithm
    old_children = get_significant_children(old_editor_div)
    new_children = get_significant_children(new_editor_div)

    # Find optimal matches
    matches = find_matching_elements(old_children, new_children)

    # Process matches in correct order
    for old_idx, new_idx in matches:
        old_child = old_children[old_idx] if old_idx is not None else None
        new_child = new_children[new_idx] if new_idx is not None else None
        diff_elements(old_child, new_child, diff_div, result_soup)

    # Replace the original editor div with the diff one
    result_editor_div = result_soup.find("div", id="editor")
    if result_editor_div:
        result_editor_div.replace_with(diff_div)

    # Append diffVisualizer.js in the body
    body = result_soup.find("body")
    if body:
        existing_script = body.find("script", src="diffVisualizer.js")
        if not existing_script:
            script_tag = result_soup.new_tag("script", src="diffVisualizer.js")
            body.append(script_tag)

    # # Remove all empty <del> and <ins> tags
    # remove_empty_track_changes(result_soup)

    # # Flatten nested tags of the same type
    # flatten_nested_track_changes(result_soup)

    # # Consolidate adjacent <del> and <ins> tags
    # consolidate_adjacent_track_changes(result_soup)

    # Path(out_path).write_text(str(result_soup), encoding="utf-8")
    # print(f"Created diff: {out_path}")
    # Remove all empty <del> and <ins> tags
    remove_empty_track_changes(result_soup)

    # Flatten nested tags of the same type
    flatten_nested_track_changes(result_soup)

    # Consolidate adjacent <del> and <ins> tags
    consolidate_adjacent_track_changes(result_soup)

    # Ensure all del and ins tags have the diff-view-all class
    all_tags = result_soup.find_all(["del", "ins"])
    all_rows = [
        row
        for row in result_soup.find_all("tr")
        if "row-added" in row.get("class", []) or "row-removed" in row.get("class", [])
    ]
    total_changes = len(all_tags) + len(all_rows)
    for tag in all_tags:
        if "class" not in tag.attrs or "diff-view-all" not in tag.get("class", []):
            if "class" in tag.attrs:
                tag["class"].append("diff-view-all")
            else:
                tag["class"] = ["diff-view-all"]
    for row in all_rows:
        if "diff-view-all" not in row.get("class", []):
            row["class"].append("diff-view-all")

    # Use formatter="html" to properly handle HTML entities
    Path(out_path).write_text(result_soup.decode(formatter="html"), encoding="utf-8")
    # print(f"Created diff: {out_path}")
    return total_changes


def main():
    if len(sys.argv) not in (3, 4):
        print("Usage:")
        print("  python html_diff_match_patch.py old.html new.html [diff.html]")
        sys.exit(1)

    old_path = sys.argv[1]
    new_path = sys.argv[2]
    out_path = sys.argv[3] if len(sys.argv) == 4 else "diff.html"

    make_trackchanges_diff(old_path, new_path, out_path)


if __name__ == "__main__":
    main()
