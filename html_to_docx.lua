local function ensure_style_application(el)
  if el.classes and #el.classes > 0 then
    -- Apply the first class as the custom Word style
    el.attr.attributes["custom-style"] = el.classes[1]
  end
  return el
end

function Meta(meta)
  meta.title = nil -- Remove the Pandoc-added "title", which is just the first heading it finds centered as a first-level header
  return meta
end

function Para(el)
  return ensure_style_application(el)
end

function Div(el)
  return ensure_style_application(el)
end

function Span(el)
  return ensure_style_application(el)
end

local function fix_column_widths(table, col_width_default)
  col_width_default = col_width_default or 0.15 -- Default to 15%

  local colspecs_width = 2                      -- In Pandoc, the column specs are contained in colspecs. Column width is determined by colspecs element at index `2`.

  local total_width = 0

  -- Step 1: Add width to columns that aren't wide enough
  for i = 1, #table.colspecs do
    local col_width = table.colspecs[i][colspecs_width]
    if not col_width or col_width < col_width_default then
      col_width = col_width_default
      table.colspecs[i][colspecs_width] = col_width
    end
    total_width = total_width + col_width
  end

  -- Step 2: If the table's width is greater than 100% (greater than 1), shrink the columns proportionately so the columns' combined widths equal 100% while maintaining the columns' relative size differences
  if total_width > 1 then
    -- Reduce the columns' widths so that the sum of the widths is 1
    for i = 1, #table.colspecs do
      table.colspecs[i][colspecs_width] = table.colspecs[i][colspecs_width] / total_width
    end
  end

  return table
end

function Table(el)
  el = fix_column_widths(el)

  return el
end
