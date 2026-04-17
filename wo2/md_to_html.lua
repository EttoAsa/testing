local pandoc = require "pandoc"

local function get_class_tag(cell)
  if #cell.content == 0 then
    return nil
  end

  local first_element = cell.content[1]
  if first_element.t ~= "Para" and first_element.t ~= "Plain" then
    return nil
  end

  local inlines = first_element.c
  
  -- Check if the first text element is a string
  if #inlines > 0 and inlines[1].t == "Str" then
    local class_tag = inlines[1].text:match("^%{([%w_%-]+)%}$")
    
    if class_tag then
      -- Remove the "{Class}" tag
      table.remove(inlines, 1)
      
      -- If there is a space immediately after, remove it to avoid breaking the alignment
      if #inlines > 0 and inlines[1].t == "Space" then
        table.remove(inlines, 1)
      end
      
      -- If removing the tag and space leaves the cell empty, delete the paragraph to avoid empty lines
      if #inlines == 0 then
        table.remove(cell.content, 1)
      end
      
      return class_tag
    end
  end

  -- Check for class tags formatted as raw markdown
  if #inlines == 1 and inlines[1].t == "RawInline" and inlines[1].format == "markdown" then
    local class_tag = inlines[1].text:match("^%{([%w_%-]+)%}$")
    if class_tag then
      -- Remove the paragraph with the class tag, which will always be the first one
      table.remove(cell.content, 1)
      return class_tag
    end
  end
  return nil
end

local function wrap_cell_content(cell, class)
  local div = pandoc.Div(cell.content, pandoc.Attr("", { class }))
  cell.content = { div }
  return cell
end

local function split_cell_content_on_br(content)
  local function is_br(inline)
    if inline.t == "LineBreak" then
      return true
    end

    if inline.t == "RawInline" and inline.format == "html" and inline.text then
      return inline.text:match("^%s*<br%s*/?>%s*$") ~= nil
    end

    return false
  end

  local function split_inlines(inlines)
    local segments = {}
    local current = {}

    for _, inline in ipairs(inlines) do
      if is_br(inline) then
        if #current > 0 then
          table.insert(segments, current)
        end
        current = {}
      else
        table.insert(current, inline)
      end
    end

    if #current > 0 then
      table.insert(segments, current)
    end

    return segments
  end

  local result = {}

  for _, block in ipairs(content) do
    if block.t == "Para" or block.t == "Plain" then
      local segments = split_inlines(block.content)
      if #segments <= 1 then
        table.insert(result, block)
      else
        for _, segment in ipairs(segments) do
          table.insert(result, pandoc.Para(segment))
        end
      end
    elseif block.t == "Div" then
      block.content = split_cell_content_on_br(block.content)
      table.insert(result, block)
    else
      table.insert(result, block)
    end
  end

  return result
end

-- Use custom_class as an optional parameter
local function process_cell(cell, custom_class)
  -- If the cell already contains a processed div, do nothing
  if #cell.content == 1 and cell.content[1].t == "Div" then
    local inner_div = cell.content[1]
    if inner_div.classes and #inner_div.classes > 0 then
      return cell
    end
  end

  -- Get the class tag from the cell (if it exists), otherwise use the custom_class
  local class_to_apply = get_class_tag(cell) or custom_class

  -- Always apply splitting for <br> tags
  cell.content = split_cell_content_on_br(cell.content)
  
  -- Performs wrapping only if an explicit class was found (e.g., {Class}) OR a custom_class is provided
  -- If neither is present, no Div is created: this preserves Pandoc's native alignment
  if class_to_apply then
    return wrap_cell_content(cell, class_to_apply)
  end

  return cell
end

local function apply_logic_to_header_cells(table, custom_class)
  for _, row in ipairs(table.head.rows or {}) do
    for i, cell in ipairs(row.cells) do
      row.cells[i] = process_cell(cell, custom_class)
    end
  end
  return table
end

local function apply_logic_to_body_cells(table, custom_class)
  for _, body in ipairs(table.bodies or {}) do
    for _, row in ipairs(body.body or {}) do
      for i, cell in ipairs(row.cells) do
        row.cells[i] = process_cell(cell, custom_class)
      end
    end
  end
  return table
end

local function wrap_table_cell_contents(el, custom_class)
  if el.head then
    el = apply_logic_to_header_cells(el, custom_class)
  end
  if el.bodies then
    el = apply_logic_to_body_cells(el, custom_class)
  end
  return el
end

local function wrap_images_in_table(el) --- Wrap images in table cells with a div with the FL class
  local function process_content(content)
    local result = {}
    for i, item in ipairs(content) do
      if item.t == "Para" then
        -- Check the first element in the div
        if #item.content > 0 and item.content[1].t == "Image" then
          local new_div = pandoc.Div({ item }, pandoc.Attr("", { "FL" }))
          result[i] = new_div
        else
          local processed_content = process_content(item.content)
          item.content = processed_content
          result[i] = item
        end
      elseif item.t == "Div" then
        -- Process content inside divs recursively
        local processed_content = process_content(item.content)
        item.content = processed_content
        result[i] = item
      else
        result[i] = item
      end
    end
    return result
  end

  local function wrap_images_in_cell(cell)
    cell.content = process_content(cell.content)
    return cell
  end
  
  if el.head then
    for _, row in ipairs(el.head.rows or {}) do
      for i, cell in ipairs(row.cells) do
        row.cells[i] = wrap_images_in_cell(cell)
      end
    end
  end

  if el.bodies then
    for _, body in ipairs(el.bodies or {}) do
      for _, row in ipairs(body.body or {}) do
        for i, cell in ipairs(row.cells) do
          row.cells[i] = wrap_images_in_cell(cell)
        end
      end
    end
  end

  return el
end

local function wrap_images_captions_in_table(el) --- Wrap images in table cells with a div with the TF class
  local function process_content(content)
    local result = {}
    for i, item in ipairs(content) do
      if item.t == "Para" then
        -- Check if paragraph starts with "Figure"
        local is_figure_caption = false
        
        if #item.content > 0 and item.content[1].t == "Strong" then
          -- Get the text from the Strong element
          local strong_text = pandoc.utils.stringify(item.content[1])
          if strong_text:match("^Figure") then
            is_figure_caption = true
          end
        end
        
        if is_figure_caption then
          -- If it's a figure caption, wrap it in a div with TF class
          local para_content = pandoc.Para(pandoc.utils.stringify(item))
          result[i] = pandoc.Div({ para_content }, pandoc.Attr("", { "TF" }))
        else
          result[i] = item
        end
      elseif item.t == "Div" then
        -- Process content inside divs recursively
        local processed_content = process_content(item.content)
        item.content = processed_content
        result[i] = item
      else
        result[i] = item
      end
    end
    return result
  end

  local function wrap_images_captions_in_cell(cell)
    cell.content = process_content(cell.content)
    return cell
  end

  if el.head then
    for _, row in ipairs(el.head.rows or {}) do
      for i, cell in ipairs(row.cells) do
        row.cells[i] = wrap_images_captions_in_cell(cell)
      end
    end
  end

  if el.bodies then
    for _, body in ipairs(el.bodies or {}) do
      for _, row in ipairs(body.body or {}) do
        for i, cell in ipairs(row.cells) do
          row.cells[i] = wrap_images_captions_in_cell(cell)
        end
      end
    end
  end
  return el
end

local function handle_ex_no_tan(el) --- Preserves the main structure of Examples and Notes
  local tag = nil
  local text_fragments = {}
  for i, block in ipairs(el.content) do
    if tag == nil then
      tag = block
    else
      table.insert(text_fragments, block)
    end
  end
  el.content = { pandoc.Div({ tag }), pandoc.Div(text_fragments) }
  return el
end

function Div(el)
  -- Notes and Examples
  if el.classes:includes("EX") or el.classes:includes("NO") or el.classes:includes("TAN") then
    return handle_ex_no_tan(el)
  end

  -- Tables enclosed in a div containing the custom class with which to wrap the table body cells
  if #el.content == 1 and el.content[1].t == "Table" then
    local custom_class = el.classes[1] or nil
    local tbl = el.content[1]
    tbl = wrap_table_cell_contents(tbl, custom_class)
    tbl.classes = el.classes -- Preserve the div classes on the table
    return tbl
  end
end

function Table(el)
  -- For free-standing tables (not enclosed in a Div), we pass `nil` as custom_class
  -- this way, if the cells don't have a {Class} tag, Pandoc maintains its native alignments.
  el = wrap_table_cell_contents(el) 
  el = wrap_images_in_table(el) 
  el = wrap_images_captions_in_table(el) 

  return el
end

-- We need to preserve the links, since Pandoc replace the HREF tag when the link is a markdown link
-- When a link is represented as a <a> tag, Pandoc won't do anything.
-- We do this here to preserve grid tables
function Link(el)
  -- Handle external links
  if el.target and el.target:match("%.md") then
    -- Convert .md to .html
    local target = el.target:gsub("%.md(#?[^)]*)", ".html%1")
    
    -- Get link text
    local link_text = pandoc.utils.stringify(el.content)
    
    -- Build HTML with attributes if present
    local attrs = ""
    if el.title and el.title ~= "" then
      attrs = attrs .. string.format(' title="%s"', el.title)
    end
    
    local html_link = string.format('<a href="%s"%s>%s</a>', target, attrs, link_text)
    
    return pandoc.RawInline('html', html_link)
  end

  -- Handle internal links (anchors)
  if el.target and el.target:match("^#") then
    
    -- Get link text
    local link_text = pandoc.utils.stringify(el.content)
    
    -- Build HTML with attributes if present
    local attrs = ""
    if el.title and el.title ~= "" then
      attrs = attrs .. string.format(' title="%s"', el.title)
    end
    
    local html_link = string.format('<a href="%s"%s>%s</a>', el.target, attrs, link_text)
    
    return pandoc.RawInline('html', html_link)
  end
  
  return el
end