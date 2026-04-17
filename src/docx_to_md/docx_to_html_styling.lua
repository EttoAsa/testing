--THIS LUA FILTER MUST BE APPLIED TO PANDOC IN THE CORRECT ORDER
local pandoc = require "pandoc"
 


--global table for references link
References = {}
Annex_Headers = {}

--helper function to get the first character of an element's content
local function getFirstChar(elem)
    if elem.t == "Str" then
        return elem.text:sub(1, 1)
    elseif elem.content and #elem.content > 0 then
        return getFirstChar(elem.content[1])
    end
    return nil
end

--helper function to clean up spaces before punctuation in a list
local function cleanupSpacesBeforePunctuation(list)
    local i = 1
    while i <= #list do
        -- Recursively clean content of nested elements
        if list[i].content then
            cleanupSpacesBeforePunctuation(list[i].content)
        end
        
        -- Check if current element is a Space element
        if list[i].t == "Space" and i < #list then
            local nextChar = getFirstChar(list[i + 1])
            if nextChar and nextChar:match("^[%.,:;!?%)%]%}]") then
                -- Remove the Space element before punctuation
                list:remove(i)
                i = i - 1  -- Adjust index since we removed an element
            end
        -- Check if current element is a Str ending with space
        elseif list[i].t == "Str" then
            local currentText = list[i].text
            -- If next element exists and starts with punctuation, remove trailing space
            if i < #list then
                local nextChar = getFirstChar(list[i + 1])
                if nextChar and nextChar:match("^[%.,:;!?%)%]%}]") then
                    if currentText:sub(-1) == " " then
                        -- Remove trailing space
                        list[i].text = currentText:sub(1, -2)
                        -- If this makes the string empty, remove the element
                        if list[i].text == "" then
                            list:remove(i)
                            i = i - 1  -- Adjust index since we removed an element
                        end
                    end
                end
            end
        end
        i = i + 1
    end
    return list
end

--helper function to avoid double spaces when inserting content
local function smartInsert(list, elem)
    if elem.t == "Str" then
        local newText = elem.text
        -- Remove spaces before punctuation within the text itself
        newText = newText:gsub(" ([%.,:;!?%)%]%}])", "%1")
        -- Check if the last element is a Str ending with space
        if #list > 0 and list[#list].t == "Str" then
            local lastText = list[#list].text
            -- If new elem starts with space, remove it to avoid double space
            if lastText:sub(-1) == " " and newText:sub(1, 1) == " " then
                newText = newText:sub(2)
            end
            -- If new elem starts with punctuation, remove trailing space from last elem
            if newText:match("^[%.,:;!?%)%]%}]") and lastText:sub(-1) == " " then
                list[#list].text = lastText:sub(1, -2)
            end
        end
        elem.text = newText
    else
        -- For non-Str elements, check if they start with punctuation
        if #list > 0 and list[#list].t == "Str" then
            local firstChar = getFirstChar(elem)
            if firstChar and firstChar:match("^[%.,:;!?%)%]%}]") then
                local lastText = list[#list].text
                if lastText:sub(-1) == " " then
                    list[#list].text = lastText:sub(1, -2)
                end
            end
        end
    end
    if elem.t ~= "Str" or elem.text ~= "" then  -- Don't insert empty strings
        list:insert(elem)
    end
end

--helper function to recognize and parse word runs with proper style
function Run(el)
    local MARK = "@#!"
    local insideRun = false
    local tag, span
    local newContent = pandoc.List({})

    for _, elem in ipairs(el.content) do
        if elem.t == "Str" and elem.text:find(MARK) then                    -- elem is a string and contains MARK
            local before, after = elem.text:match("(.-)" .. MARK .. "(.*)") -- before and after are what is writter before or after MARK
            if before or after then                                         -- elem is the start or the end of a word run
                insideRun = not insideRun
                if insideRun then                                           -- we found a new run section
                    if before ~= "" then                                    --we append what's before MARK too
                        smartInsert(newContent, pandoc.Str(before))
                    end
                    tag = ""               --reset tag
                    span = pandoc.Span("") --create new span
                else                       --we just reached the end of a run, so we must use our span
                    if before ~= "" then   --append what's before MARK to the span
                        span.content:insert(pandoc.Str(before))
                    end
                    --remove space after tag if the span is not only composed of a single space
                    if #span.content > 1 then
                        span.content:remove(1)
                    end
                    --remove trailing space from last element if present
                    if #span.content > 0 and span.content[#span.content].t == "Str" then
                        local lastText = span.content[#span.content].text
                        if lastText:sub(-1) == " " then
                            span.content[#span.content].text = lastText:sub(1, -2)
                        end
                    end
                    
                    -- For simple bold/italic/underline only tags, Pandoc already created
                    -- the formatting tags when reading the docx, so just unwrap the markers
                    if tag == "ondemand_CHAR_bold" or tag == "ondemand_CHAR_italic" or tag == "ondemand_CHAR_underline" then
                        for _, item in ipairs(span.content) do
                            smartInsert(newContent, item)
                        end
                    elseif span.content then
                        -- Check if the tag indicates italic, bold, or underline formatting
                        local has_italic = tag:find("italic") ~= nil
                        local has_bold = tag:find("bold") ~= nil
                        local has_underline = tag:find("underline") ~= nil
                        
                        -- Check if tag has other CSS properties (size, color, name)
                        local has_other_props = tag:find("size_") or tag:find("color_") or tag:find("name_")
                        
                        local element_to_insert
                        
                        -- Apply formatting: if both bold and italic, nest them appropriately
                        if has_italic and has_bold then
                            -- Nest: Strong(Emph(content))
                            element_to_insert = pandoc.Strong({pandoc.Emph(span.content)})
                        elseif has_italic then
                            -- Just italic
                            element_to_insert = pandoc.Emph(span.content)
                        elseif has_bold then
                            -- Just bold
                            element_to_insert = pandoc.Strong(span.content)
                        else
                            -- No italic/bold, keep as span with class
                            span.attr = { class = tag }
                            element_to_insert = span
                        end
                        
                        -- If underline or other CSS properties are present along with italic/bold, wrap in span
                        if (has_underline or has_other_props) and (has_italic or has_bold) then
                            local wrapper_span = pandoc.Span({element_to_insert})
                            wrapper_span.attr = { class = tag }
                            smartInsert(newContent, wrapper_span)
                        else
                            smartInsert(newContent, element_to_insert)
                        end
                    end
                    
                    local secondStart, secondEnd = after:find(MARK)
                    if secondStart then                             --we have another run just after this one
                        if after:sub(1, secondStart - 1) ~= "" then --there is something between the two runs so we append it
                            smartInsert(newContent, pandoc.Str(after:sub(1, secondStart - 1)))
                        end
                        --reset everything and set inside to True
                        insideRun = true
                        tag = ""
                        span = pandoc.Span("")
                    elseif after ~= "" then -- we append what's after MARK too
                        smartInsert(newContent, pandoc.Str(after))
                    end
                end
            end
        elseif insideRun then           --we incorporate everything in the span as it is
            if tag == "" then           --tag is 1st string after MARK
                if elem.t == "Str" then --we need to assign tag
                    tag = elem.text
                end
            else -- we need to append all the text to our span
                span.content:insert(elem)
            end
        else --we are not in a special run so we just copy the rest of the content as it is
            smartInsert(newContent, elem)
        end
    end
        -- Clean up spaces before punctuation before creating the Div
        cleanupSpacesBeforePunctuation(el.content)
        
        
    
    -- Final cleanup: remove spaces before punctuation
    local i = 1
    while i <= #newContent do
        if newContent[i].t == "Space" and i < #newContent then
            -- Check if next element starts with punctuation
            local nextChar = getFirstChar(newContent[i + 1])
            if nextChar and nextChar:match("^[%.,:;!?%)%]%}]") then
                -- Remove the Space element before punctuation
                newContent:remove(i)
                i = i - 1
            end
        elseif newContent[i].t == "Str" and newContent[i].text:sub(-1) == " " and i < #newContent then
            -- Check if next element starts with punctuation
            local nextChar = getFirstChar(newContent[i + 1])
            if nextChar and nextChar:match("^[%.,:;!?%)%]%}]") then
                -- Remove trailing space from current element
                newContent[i].text = newContent[i].text:sub(1, -2)
                -- If this makes the string empty, remove the element
                if newContent[i].text == "" then
                    newContent:remove(i)
                    i = i - 1
                end
            end
        end
        i = i + 1
    end
    
    return newContent
end

--heleper function to apply paragraphs styles
function Style(el)
    -- search for paragraph style
    local text = pandoc.utils.stringify(el)
    local startIndex, endIndex, tag = text:find("%[{%[%-%-(.-)%-%-%]}%]")                                                   --pattern used in preprocessing.py to mark paragraphs

    if endIndex == #text then                                                                                               -- paragraph styles are always tagged at the end of the paragraph
        table.remove(el.content)                                                                                            -- remove the tag string [{[--tag--]}] from para or header
        table.remove(el.content)                                                                                            -- remove the space before tag from para or header
        if tag == "TF" and el.content[1] and el.content[3] then                                                             --this is the description of an image
            return pandoc.Div(el.content,
                { 
                    class = tag, 
                    -- id = el.content[1].text .. "_" .. el.content[3].text:sub(1, -2) 
                })                           --id is Figure_x.x.x
        elseif tag == "TH" and el.content[1] and el.content[3] then                                                         -- this is a table title
            return pandoc.Div(el.content,
                { 
                    class = tag, 
                    -- id = el.content[1].text .. "_" .. el.content[3].text:sub(1, -2)
                })                           --id is Table_x.x.x
        end
        return pandoc.Div(el.content, { class = tag })                                                                      --apply style to para header, by returning a div without the tag, but with the corresponding style class
    else
        return el
    end
end

--helper function to generate references
function Reference(el)
    local text = pandoc.utils.stringify(el)
    for prefix, number in text:gmatch("%[?%s*(i?%.?)(%d+)%]") do
        if number then
            local key = (prefix or "") .. number -- just the number or the prefix + number if prefix is not null
            if text:sub(2, #key + 1) == key then --this is a reference in 2.1 or 2.2
                -- Pandoc separates the opening bracket from the rest
                -- of the reference tag due to the hyperlink in the docx,
                -- this is to fix that
                if el.content[1] and el.content[1].content and el.content[1].content[1] and el.content[1].content[1].text == "[" then -- The separated bracket
                    if el.content[2] and el.content[2].content and el.content[2].content[1] and el.content[2].content[1].text then
                        el.content[2].content[1].text = "[" .. el.content[2].content[1].text
                        table.remove(el.content, 1)
                    end
                end
                --   Reference i.18 still needs to be fixed because its bracketed portion is split up like this: [i. , 18]
                if key == "i.18" then
                    if el.content[2] and el.content[2].content and el.content[2].content[1] and el.content[2].content[1].text then
                        el.content[2].content[1].text = "[i." .. el.content[2].content[1].text
                        table.remove(el.content, 1)
                    end
                end
                ----

                -- Some references have portions of text attached to the element with the tag,
                -- so they must be separated
                if el.content[1] and el.content[1].content and el.content[1].content[1] and el.content[1].content[1].text then
                    local ideal_length = string.len("[" .. prefix .. number .. "]\t")
                    local actual_length = string.len(el.content[1].content[1].text)
                    if ideal_length ~= actual_length then
                        local text_to_split = el.content[1].content[1].text
                        table.remove(el.content, 1)
                        table.insert(el.content, 1,
                            pandoc.Plain({ pandoc.Str(text_to_split:sub(ideal_length, actual_length)) }))
                        table.insert(el.content, 1, pandoc.Plain({ pandoc.Str(text_to_split:sub(1, ideal_length)) }))
                    end
                end


                if not key:find("i.") then --the reference is normative
                    key = "n." .. key -- we add a prefix to the key to distinguish normative from normal numbers (this is an issue when converting to docx)
                end
                References[key] = "#"..key --we save the reference in the global table
                return pandoc.Div(el.content, {id = key, class = el.attr["classes"][1]})
            end
        end
    end
    return el
end

--Pandoc filters
if FORMAT:match 'html' then
    function Str(el)
        --rever TAB marks back to \tS
        local text = el.text:gsub("{{{{TAB}}}}", "\t")
        return pandoc.Str(text)
    end

    function Para(el)
        --search for runs marked by @#!
        el.content = Run(el)
        --search for paragraph style
        el = Style(el)
        el = Reference(el)
        return el
    end

    function Plain(el)
        --search for runs marked by @#!
        el.content = Run(el)
        --search for paragraph style
        return Style(el)
    end

    function Emph(el)
        --search for runs marked by @#!
        el.content = Run(el)
        return el
    end

    function Strong(el)
        --search for runs marked by @#!
        el.content = Run(el)
        return el
    end

    function Superscript(el)
        el.content = Run(el)
        return el
    end

    function Header(el)
        el.content = Run(el)
        -- fix annex headers
        if el.level == 8 then
            Annex_Headers[el.content[3].text] = "#" .. el.attr.identifier -- annex letter / link correspondance
            el.level = 1
            return el
        end
        -- fix header level of sub-clauses of annexes
        if el.content[1].t == "Str" and el.content[1].text:find("^%u%.%d") then
            el.level = el.level + 1
            return el
        end
        --search for style
        return Style(el)
    end

    function Image(el)
        -- retrieve aspect ratio of image
        local width = tonumber(el.attr.attributes.width:sub(1, -3))
        local height = tonumber(el.attr.attributes.height:sub(1, -3))
        local ratio = height / width
        -- set height
        -- TODO: need to check this one, it feels unnecessary
        -- el.attr = { style = "width: 100%; height: calc(100%*"..ratio..");"}

        local filePath, extension = el.src:match("(.*)%.(.*)$") -- image.png, jpeg or emf
        --fixes extensions
        if extension == "emf" then
            el.src = filePath .. ".png"
            return el
        end
        --adds yellow overlay on top of the image
        if extension == "png" then
            local overlay = pandoc.Span({}, {
                style =
                "position: absolute; top: 0; right: 0; bottom: 0; left: 0; background-color: rgba(255, 255, 0, 0.5); pointer-events: none; z-index: 1;",
                class = "image_overlay"
            })
            return pandoc.Span({ el, overlay }, { style = "position: relative; display: inline-flex;" })
        end
        return el;
    end

    function Pandoc(el)
        --save references for second filter
        local fp = 'media/references.json'
        local mt = 'text/json'
        pandoc.mediabag.insert(fp, mt, pandoc.json.encode(References))
        --save annex_headers for second filter
        local fp = 'media/annex.json'
        pandoc.mediabag.insert(fp, mt, pandoc.json.encode(Annex_Headers))
        --save toc
        local fp = 'media/toc.json'
        pandoc.mediabag.insert(fp, mt, pandoc.json.encode(pandoc.structure.table_of_contents(el, { toc_depth = 4 })))
    end
end