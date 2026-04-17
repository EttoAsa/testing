local pandoc = require "pandoc"

local function is_allowed_inline_tag(tag_inner)
  local trimmed = tag_inner:match("^%s*(.-)%s*$") or tag_inner
  local lowered = trimmed:lower()

  if lowered == "sup" or lowered == "/sup" then
    return true
  end
  if lowered == "mark" or lowered == "/mark" then
    return true
  end
  if lowered == "span" or lowered == "/span" or lowered:match("^span%s") then
    return true
  end
  if lowered == "img" or lowered:match("^img%s") or lowered:match("^img%s.*/$") then
    return true
  end

  return false
end

local function escape_angle_brackets_for_non_tags(text)
  return text:gsub("<([^<>]-)>", function(tag_inner)
    if is_allowed_inline_tag(tag_inner) then
      return "<" .. tag_inner .. ">"
    end
    return "&lt;" .. tag_inner .. "&gt;"
  end)
end

local function add_tag_to_cell(cell, class)
  local tag = pandoc.RawInline("markdown", "{" .. class .. "}")

  table.insert(cell.content, 1, pandoc.Para { tag })

  return cell
end

local function remove_divs_from_cell(cell, default_class) --- Takes a Pandoc table cell, `cell`, and an array `classes`, an array of strings of the CSS class names applied by divs within the table
  local new_blocks = {}
  local found_class = ""

  for _, block in ipairs(cell.content) do
    if block.t == "Div" and block.attr and block.attr.classes and block.attr.classes[1] ~= "TAN" then
      -- Each cell only has one class that any divs inside of it apply, so it suffices to store the first class found.
      found_class = block.attr.classes[1] or ""

      -- Unwrap div
      for _, inner in ipairs(block.content) do
        table.insert(new_blocks, inner)
      end
    else
      table.insert(new_blocks, block)
    end
  end

  cell.content = new_blocks

  if found_class ~= "" and found_class ~= default_class then
    cell = add_tag_to_cell(cell, found_class)
  end

  return cell
end

local function count_class(cell, class_counts) --- Count the instances of all classes, but exclude the class `TAH` from consideration. `TAH`, which is for header cells, should never be a default class for table bodies.
  for _, block in ipairs(cell.content) do
    if block.t == "Div" and block.attr then
      local classes = block.attr.classes or {}

      for _, class in ipairs(classes) do
        if class == "TAH" then
          goto continue --- Do not consider TAH in the count
        end

        local is_found = false
        for _, entry in ipairs(class_counts) do
          if entry[1] == class then
            entry[2] = entry[2] + 1
            is_found = true
            break
          end
        end
        if not is_found then
          table.insert(class_counts, { class, 1 })
        end

        ::continue::
      end
    end
  end
end

local function get_table_body_default_class_by_occurrence_rate(class_counts)
  local default_class = ""
  local default_class_occurrences = 0
  local target_proportion = 0.5

  local total_class_instances = 0

  for _, entry in ipairs(class_counts) do -- Step 1: Sum class instances
    total_class_instances = total_class_instances + entry[2]
  end

  for _, entry in ipairs(class_counts) do -- Step 2: Determine default class according to occurrence rate
    if entry[2] / total_class_instances >= target_proportion then
      default_class = entry[1]
    end
  end

  return default_class
end

local function get_table_body_default_class_by_num_occurrences(class_counts)
  local default_class = ""
  local default_class_occurrences = 0

  for _, entry in ipairs(class_counts) do -- Determine default class according to most occurrences
    if entry[2] > default_class_occurrences then
      default_class = entry[1]
      default_class_occurrences = entry[2]
    end
  end

  return default_class
end

function Table(el)
  local table_rows = {}
  local class_counts = {}

  -- Get header rows
  for _, row in ipairs(el.head.rows) do
    table.insert(table_rows, { row = row, is_header = true })
  end

  -- Get body rows and class counts
  for _, body in ipairs(el.bodies) do
    for _, row in ipairs(body.body) do
      table.insert(table_rows, { row = row, is_header = false })
      for _, cell in ipairs(row.cells) do
        count_class(cell, class_counts)
      end
    end
  end

  local default_body_class = get_table_body_default_class_by_num_occurrences(class_counts)

  -- Tag table header cells with non-default CSS class, if applicable
  for _, row in ipairs(el.head.rows) do
    for _, cell in ipairs(row.cells) do
      cell = remove_divs_from_cell(cell, "TAH")
    end
  end

  -- Tag table body cells with non-default CSS class, if applicable
  for _, body in ipairs(el.bodies) do
    for _, row in ipairs(body.body) do
      for _, cell in ipairs(row.cells) do
        cell = remove_divs_from_cell(cell, default_body_class)
      end
    end
  end

  local final_table = el

  if default_body_class ~= "" then
    final_table = pandoc.Div({ el }, pandoc.Attr("", { default_body_class }))
  end

  return final_table
end

local function format_example_or_note(div, cls) --- Convert examples and notes to GitLab-compatible note syntax
  local gitlab_tag = nil

  if cls == "NO" or cls == "TAN" then
    gitlab_tag = "[!note]" -- For notes
  else
    gitlab_tag = "[!tip]"  -- For examples
  end

  local is_applicable_div = #div.content >= 2 and div.content[1].t == "Para" and
      div.content[1].content and
      (
        pandoc.utils.stringify(div.content[1].content):match("^EXAMPLE%s?%d?%d?") or
        pandoc.utils.stringify(div.content[1].content):match("^NOTE%s?%d?%d?")
      ) and
      (div.content[2].t == "Para" or div.content[2].t == "CodeBlock")

  if is_applicable_div then
    -- Assume that examples/notes like these are in the preprocessed form of two paragraphs or one paragraph and one code block within a div
    local tag = pandoc.utils.stringify(div.content[1].content)
    local first_element = pandoc.Para({ pandoc.RawInline("markdown", ">>> " .. gitlab_tag .. " " .. tag) })
    local new_structure_elements = { first_element }

    for i = 2, #div.content do
      table.insert(new_structure_elements, div.content[i])
    end

    local last_element = pandoc.Para({ pandoc.RawInline("markdown", ">>>") })
    table.insert(new_structure_elements, last_element)

    return new_structure_elements
  end

  return div
end

function Div(el)
  local table_note_class = "TAN"
  local note_class = "NO"
  local example_class = "EX"

  if el.classes and el.classes:includes(table_note_class) then
    el = format_example_or_note(el, table_note_class)
  end

  if el.classes and el.classes:includes(note_class) then
    el = format_example_or_note(el, note_class)
  end

  if el.classes and el.classes:includes(example_class) then
    el = format_example_or_note(el, example_class)
  end

  -- Unwrap divs with classes that don't need to be preserved in Markdown
  -- These include First_Paragraph, list-item, Compact, Source_Code, etc.
  local classes_to_unwrap = {
    "First_Paragraph",
    "list-item",
    "Compact",   -- Must unwrap for nested lists to work correctly
    "Source_Code",
    "TAL",  -- Table alignment
    "TAC",  -- Table alignment center
    "TAH",  -- Table header
    "TAB",  -- Table body
    "FL",   -- Figure label
    "TF",   -- Table/Figure formatting
    "TH",   -- Table header
    "EW",   -- Abbreviations
    "NF",   -- Normal formatting
  }
  
  if el.classes then
    for _, class_to_unwrap in ipairs(classes_to_unwrap) do
      if el.classes:includes(class_to_unwrap) then
        -- Return just the content, unwrapping the div
        return el.content
      end
    end
  end

  return el
end

function Image(el)
  -- -- Convert images to HTML tags with height in pixels
  -- local html_tag = "<img src=\"" .. el.src .. "\""

  -- -- Add alt text if present
  -- if el.caption and #el.caption > 0 then
  --   local alt_text = pandoc.utils.stringify(el.caption)
  --   html_tag = html_tag .. " alt=\"" .. alt_text .. "\""
  -- end

  -- html_tag = html_tag .. ">"

  -- return pandoc.Str(html_tag)
  return el
end

function Str(el)
  -- Str nodes contain plain text, so literal angle brackets are not HTML tags.
  -- Escape them directly to also cover cases where <...> is split across
  -- multiple inline nodes (e.g. by Strong/Emph formatting).
  local escaped = el.text:gsub("<", "&lt;"):gsub(">", "&gt;")
  if escaped ~= el.text then
    return pandoc.Str(escaped)
  end
  return el
end

function RawInline(el)
  -- Preserve real inline HTML tags from this allow-list only; escape all other <...>.
  if el.format == "html" then
    local escaped = escape_angle_brackets_for_non_tags(el.text)
    if escaped ~= el.text then
      return pandoc.RawInline("html", escaped)
    end
  end
  return el
end

function Superscript(el) --- Maintain HTML `<sup>` superscript tags instead of using Markdown `^superscript^` syntax to allow superscript text to render in Markdown viewers.
  local superscript_text = pandoc.utils.stringify(el.content)

  return pandoc.RawInline("markdown", "<sup>" .. superscript_text .. "</sup>")
end

function Emph(el) --- Preserve emphasis (italic) as native Markdown syntax
  -- Return as-is to let Pandoc convert it to Markdown _text_ syntax
  return el
end

function Span(el) --- Handle spans with specific classes during HTML to Markdown conversion
  -- Check if the span has the HTML-Sample class (with hyphen, not underscore)
  if el.classes and el.classes:includes("HTML-Sample") then
    local span_text = pandoc.utils.stringify(el.content)
    
    -- Use native Markdown syntax: _`text`_ for italic + code
    return pandoc.RawInline("markdown", "_`" .. span_text .. "`_")
  end
  
  -- For other spans, return as-is to preserve class
  return el
end

-- Force list items with nested lists to use "loose" formatting
-- This makes Pandoc preserve list markers for nested lists
local function ensure_loose_list_with_nesting(item)
  -- Check if this item has nested lists
  local has_nested_list = false
  
  for _, block in ipairs(item) do
    if block.t == "BulletList" or block.t == "OrderedList" then
      has_nested_list = true
      break
    end
  end
  
  if not has_nested_list then
    return item
  end
  
  -- Convert all Plain blocks to Para to force "loose" list formatting
  -- This signals to Pandoc that list items should maintain proper structure
  local new_item = {}
  for _, block in ipairs(item) do
    if block.t == "Plain" then
      table.insert(new_item, pandoc.Para(block.content))
    else
      table.insert(new_item, block)
    end
  end
  
  return new_item
end

function BulletList(el)
  -- Ensure items with nested lists use loose formatting
  for i, item in ipairs(el.content) do
    el.content[i] = ensure_loose_list_with_nesting(item)
  end
  return el
end

function OrderedList(el)
  -- Ensure items with nested lists use loose formatting
  for i, item in ipairs(el.content) do
    el.content[i] = ensure_loose_list_with_nesting(item)
  end
  return el
end
