local pandoc = require "pandoc"
-- local logfile = io.open("debug.log", "a")

local mt, filename_numbers_mapping = pandoc.mediabag.fetch("filename_numbers_mapping.json")
filename_numbers_mapping = pandoc.json.decode(filename_numbers_mapping, false)

local function split(str, delimiter)
  local result = {}
  local from = 1
  local delim_from, delim_to = string.find(str, delimiter, from)
  
  while delim_from do
    table.insert(result, string.sub(str, from, delim_from - 1))
    from = delim_to + 1
    delim_from, delim_to = string.find(str, delimiter, from)
  end
  
  table.insert(result, string.sub(str, from))
  return result
end

function countPlusChars(str)
    local count = 0
    str:gsub("%+%+%+", function() count = count + 1 end)
    return count
end

function countWordChars(text, word)
    local count = 0
    text:gsub(word, function() count = count + 1 end)
    return count
end

-- Finds the correct end of the link, ignoring parentheses and subsequent text
local function get_link_end_index(text)
    -- Allow alphanumerics,'+', dot, dash, underscore, and comma
    local valid_chars = "[%w%+%.%-%_%,]"
    local end_index = 0
    
    -- Scans forward and stops as soon as it encounters an invalid character
    for i = 1, #text do
        local c = text:sub(i, i)
        if not c:match(valid_chars) then
            break
        end
        end_index = i
    end

    -- Backtracking: Ensure that the last character of the link is a letter or a number.
    -- This removes any dots, dashes, or commas at the end of the string
    while end_index > 0 and not text:sub(end_index, end_index):match("[%w]") do
        end_index = end_index - 1
    end

    return end_index
end

function CustomTagsToLinks(el, prefix)
  local new_content = pandoc.List()
  local children = el.content

  for _, child in ipairs(children) do
    if child.t == "Str" and child.text:find(prefix:lower() .. "+++") then
      error(string.format("%s\nInvalid reference: '%s' should start with an uppercase letter.", pandoc.utils.stringify(child), child.text))
    end

    if child.t == "Str" and child.text:find(prefix .. "+++") then

      if child.text:find("Clause") and (child.text:find("+++below") or child.text:find("+++above")) then
        -- flash an error and stop execution, they are only allowed when there are only 2 parts
        error(string.format("%s\nInvalid reference: 'below' and 'above' are only allowed for Tables and Figures.", pandoc.utils.stringify(child)))
      end

      if child.text:find("+++below") or child.text:find("+++above") then
        local plusCount = countPlusChars(child.text)
        if plusCount > 1 and countWordChars(child.text, "+++below") ~= plusCount and countWordChars(child.text, "+++above") ~= plusCount then
          -- flash an error and stop execution, they are only allowed when there are only 2 parts
          error(string.format("%s\nInvalid reference: 'below' and 'above' are only allowed within the same file, for custom references that have the (Table|Figure)+++(below|above)[+++(below|above)]+ format. You can't mix up below and after in the same link.", pandoc.utils.stringify(child)))
        end

        local remaining_text = child.text

        -- keep punctuation/text before the custom tag outside the link
        local start_index = remaining_text:find(prefix .. "+++")
        if start_index > 1 then
          new_content:insert(pandoc.Str(child.text:sub(1, start_index - 1)))
          remaining_text = child.text:sub(start_index)
        end

        local end_index = get_link_end_index(remaining_text)

        local extract_text = remaining_text:sub(1, end_index)
        local id = extract_text:match(prefix .. "+++(below|above)")

        local html_link = string.format('<a id="%s" href="#%s">%s</a>', id, extract_text, extract_text)
        new_content:insert(pandoc.RawInline('html', html_link))

        if end_index < #remaining_text then
          local after_text = remaining_text:sub(end_index + 1)
          new_content:insert(pandoc.Str(after_text))
        end
        goto continue
      end


      local remaining_text = child.text

      -- check if there is some text before the link (punctuation or words) and keep it
      local start_index = remaining_text:find(prefix .. "+++")

      if start_index > 1 then
        new_content:insert(pandoc.Str(child.text:sub(1, start_index - 1)))
        remaining_text = child.text:sub(start_index)
      end


      local end_index = get_link_end_index(remaining_text)
      
      -- remaining_text may have been sliced from start_index, so extract from 1 here
      local extract_text = remaining_text:sub(1, end_index)

      -- extract the individual parts of the link (up to 2 parts: optional filename, id)
      local parts = split(extract_text, "+++")

      local filename = nil
      local id = nil
      if #parts > 2 then
        filename = parts[2]
        id = parts[3]
      elseif #parts == 2 then
        id = parts[2]
      else
        error(string.format("%s\nInvalid reference: '%s' does not have the correct format. It should be %s+++<id> or %s+++<filename>+++<id>", pandoc.utils.stringify(child), child.text, prefix, prefix))
      end

      local id_prefix = ""
      local html_filename = ""

      if prefix == "Figure" and #parts == 2  and (id:find("^[%w_-]+%.png$") or id:find("^[%w_-]+%.jpg$") or id:find("^[%w_-]+%.jpeg$") or id:find("^[%w_-]+%.svg$")) then
        id_prefix = "Figure+++"
      elseif prefix ~= "Clause" then
        id_prefix = prefix .. "_"
      end

      if filename then
        if filename_numbers_mapping[filename] == nil then
          error(string.format("Filename '%s' not found. Can't create a link for element %s", filename, pandoc.utils.stringify(child)))
        end
        local clause_number = filename_numbers_mapping[filename]
        -- check that number is not a letter to differentiate between clauses and annexes
        if type(clause_number) ~= "number" then
          -- replace the first char with a uppercase letter
          clause_number = clause_number:sub(1,1):upper() .. clause_number:sub(2)
          html_filename = "annex-" .. clause_number .. ".html"
          if id:find("root.") then
            id = id:gsub("root%.", clause_number .. ".")
          elseif id:match("root$") then
            id = id:gsub("root", clause_number)
          end
          prefix = prefix:gsub("Clause", "Annex"):gsub("clause", "annex")
        else
          html_filename = "clause-" .. math.floor(clause_number) .. ".html"
          if id:find("root.") then
            id = id:gsub("root%.", math.floor(clause_number) .. ".")
          elseif id:match("root$") then
            id = id:gsub("root", math.floor(clause_number))
          end
        end
      end

      -- create the HTML link
      local html_link = string.format('<a id="%s" href="%s#%s%s">%s</a>', extract_text, html_filename, id_prefix, id, prefix:lower() .. " " .. id)
      new_content:insert(pandoc.RawInline('html', html_link))

      -- if we extracted the link (end_index < #remaining_text), keep the remaining text after the link
      if end_index < #remaining_text then
        local after_text = remaining_text:sub(end_index + 1)
        new_content:insert(pandoc.Str(after_text))
      end
    else
      new_content:insert(child)
    end
    ::continue::
  end

  -- Replace the original content with the new one
  el.content = new_content
  return el
end

function RemoveLeadingTilde(el)
  local new_content = pandoc.List()
  local children = el.content
  local words = {"clause", "table", "figure", "annex"}

  for _, child in ipairs(children) do
    if child.t == "Str" then
      local text = child.text
      for _, word in ipairs(words) do
        local pattern = "~" .. word
        local start_index, end_index = text:lower():find(pattern)
        if start_index then
          if start_index > 1 then
            new_content:insert(pandoc.Str(text:sub(1, start_index - 1)))
          end
          local original_word = text:sub(start_index + 1, end_index)
          local remaining_text = text:sub(end_index + 1)
          new_content:insert(pandoc.Span({ pandoc.Str(original_word .. remaining_text) }, pandoc.Attr("", { "external-link" })))
          goto continue
        end
      end
      new_content:insert(child)
    else
      new_content:insert(child)
    end
    ::continue::
  end

  -- Replace the original content with the new one
  el.content = new_content
  return el
end

function Para(el)
    el = CustomTagsToLinks(el, "Table")
    el = CustomTagsToLinks(el, "Figure")
    el = CustomTagsToLinks(el, "Clause")
    el = RemoveLeadingTilde(el)
    return el
end

function Div(el)
    el = CustomTagsToLinks(el, "Table")
    el = CustomTagsToLinks(el, "Figure")
    el = CustomTagsToLinks(el, "Clause")
    el = RemoveLeadingTilde(el)
    return el
end

function Plain(el)
  el = CustomTagsToLinks(el, "Table")
  el = CustomTagsToLinks(el, "Figure")
  el = CustomTagsToLinks(el, "Clause")
  el = RemoveLeadingTilde(el)
  return el
end

function Strong(el)
  el = CustomTagsToLinks(el, "Table")
  el = CustomTagsToLinks(el, "Figure")
  el = CustomTagsToLinks(el, "Clause")
  return el
end

function Emph(el)
  -- el = CustomTagsToLinks(el, "Table")
  -- el = CustomTagsToLinks(el, "Figure")
  -- el = CustomTagsToLinks(el, "Clause")
  el = RemoveLeadingTilde(el)
  return el
end

function Underline(el)
  el = CustomTagsToLinks(el, "Table")
  el = CustomTagsToLinks(el, "Figure")
  el = CustomTagsToLinks(el, "Clause")
  el = RemoveLeadingTilde(el)
  return el
end

function Span(el)
  el = CustomTagsToLinks(el, "Table")
  el = CustomTagsToLinks(el, "Figure")
  el = CustomTagsToLinks(el, "Clause")
  el = RemoveLeadingTilde(el)
  return el
end