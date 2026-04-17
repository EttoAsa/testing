--THIS LUA FILTER MUST BE APPLIED TO PANDOC IN THE CORRECT ORDER
local debug = false
local pandoc = require "pandoc"


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

--generates link for caluses
function ClauseLink(text, number)
    return text
end

--generates link for figures
function FigureLink(text, number)
    return text
end

--generates link for tables
function TableLink(text, number)
    return text
end

--generates link for annexes
function AnnexLink(text, number)
    return text
end

--helper function that uses the generated toc to link clauses and figures to the respetive header
function Substitute(el, word)
    local newContent = pandoc.List({})
    local pattern = "(%w*%.?%d*%.?%d*%.?%d+%-?%d*)"
    if word == "annex" then
        pattern = "(%u)"
    end

    local i = 1
    while el.content[i] do
        local elem = el.content[i]
        if elem.t == "Str" and elem.text:lower():find(word) then --check the next strings to see if we need to link it
            local startIndex, endIndex, number = elem.text:gsub("‑", "-"):find(pattern) --check if number is in the same Str elem
            local succ = el.content[i + 2] --next string if it exists should be number
            if succ and succ.t == "Str" then
                number = succ.text:gsub("‑", "-"):match(pattern)
                if succ.t == "Str" and number then                                        --we continue searching
                    local succ_succ = el.content
                        [i + 4]                                                           -- next next string if it exists and is of could link to other documents
                    if succ_succ and succ_succ.t == "Str" and succ_succ.text == "of" then -- this refers to another document
                        if debug then
                            print(word .. " referring to another document", succ.text, succ_succ.text,
                                el.content[i + 6])
                        end
                    else --we finally sustitute it with the proper link
                        if word == "clause" then
                            newContent:insert(ClauseLink(elem.text .. " " .. number, number))
                        elseif word == "figure" then
                            newContent:insert(FigureLink(elem.text .. " " .. number, number))
                        elseif word == "table" then
                            newContent:insert(TableLink(elem.text .. " " .. number, number))
                        elseif word == "annex" then
                            newContent:insert(AnnexLink(elem.text .. " " .. number, number))
                        else
                            if debug then print("Unkown behavior for " .. word .. " or link does not exists") end
                        end
                        if debug then print(succ.text, number) end
                        local text, substitutions = succ.text:gsub("‑", "-") --if we substituted we need to account for this, because nbh is not acii anf thus is more then one byte
                        local startIndex, endIndex = text:find(pattern)
                        if endIndex + substitutions * 2 < #succ.text then -- if something remains (like a comma or a bracket), append it too
                            newContent:insert(pandoc.Str(succ.text:sub(endIndex + substitutions * 2 + 1, -1)))
                        end
                        i = i + 2 --we skip a space and a string because we insert them manually in the link content
                        goto continue
                    end
                else
                    if debug then
                        print("Error: type is not Str or number does not follow")
                        print(elem.text, succ.t, succ.text, number)
                    end
                end
            end
        end
        --append the other elements normally
        newContent:insert(elem)
        ::continue::
        i = i + 1
    end
    
    -- Final cleanup: remove spaces before punctuation
    cleanupSpacesBeforePunctuation(newContent)
    
    return newContent
end

function MultipleClauses(el)
    local newContent = pandoc.List({})
    local pattern = "(%w*%.?%d*%.?%d*%.?%d+%-?%d*)"
    local clausesFound = false --this is true when we found the word "clauses" and remain true until we habe clauses numbers following

    local i = 1
    while el.content[i] do
        local elem = el.content[i]

        if elem.t == "Str" then
            --this may be the start of a list of multiple clauses
            if elem.text:lower():find("clauses") then
                clausesFound = true
                newContent:insert(elem)
                goto continue
            end

            if clausesFound then
                --check if we found a clause number
                local startIndex, endIndex, number = elem.text:find(pattern)

                if elem.text:match("^,$") or elem.text:match("and") then
                    --this is just a comma or the word 'and' separating the clauses
                    --do nothing
                elseif number then
                    -- we did in fact find a clause number
                    --substitute with linkS
                    newContent:insert(ClauseLink(elem.text:sub(startIndex, endIndex), number))
                    if endIndex < #elem.text then
                        --add the rest of the string too
                        newContent:insert(pandoc.Str(elem.text:sub(endIndex + 1, -1)))
                    end
                    goto continue --skip to the nex element
                else
                    --we found something that is neither a comma, the word 'and' or a clause number,
                    --so we can say this is not a list of multiple clauses
                    clausesFound = false
                end
            end
        end

        newContent:insert(elem)
        ::continue::
        i = i + 1
    end
    
    -- Final cleanup: remove spaces before punctuation
    cleanupSpacesBeforePunctuation(newContent)
    
    return newContent
end

--helper functions to fix Plain encapsulated div contents, this is an artefact due to how pandoc creates cutom divs in filter_1.lua
local function isAllPlain(el)
    if not el.content then --if content is empty
        return false
    end
    for _, elem in ipairs(el.content) do --check every elem for Plain type
        if elem.t ~= "Plain" then
            return false
        end
    end
    return true
end

function Normalize(el)
    local newContent = pandoc.List()
    if isAllPlain(el) then
        for _, elem in ipairs(el.content) do
            for _, element in ipairs(elem.content) do
                newContent:insert(element)
            end
        end
    else
        -- Not all Plain, but merge consecutive Plain elements when the second starts with punctuation
        newContent = pandoc.List(el.content)
        local i = 1
        while i < #newContent do
            if newContent[i].t == "Plain" and newContent[i + 1] and newContent[i + 1].t == "Plain" then
                -- Check if the second Plain starts with punctuation
                local firstChar = getFirstChar(newContent[i + 1])
                if firstChar and firstChar:match("^[%.,:;!?%)%]%}]") then
                    -- Merge the two Plain elements
                    for _, elem in ipairs(newContent[i + 1].content) do
                        newContent[i].content:insert(elem)
                    end
                    -- Remove the second Plain element
                    newContent:remove(i + 1)
                    -- Don't increment i, check again from the same position
                else
                    i = i + 1
                end
            else
                i = i + 1
            end
        end
        return newContent
    end
    return newContent
end

function Linking(el)
    return el
end

function RemoveAfterFirstTab(text)
    -- Find the position of the first occurrence of '\t'
    local firstTabPos = text:find("\t")

    -- Check if a tab was found
    if firstTabPos then
        -- Return everything before the first '\t' as a Pandoc string
        return text:sub(1, firstTabPos - 1)
    else
        -- If there are no tabs, return the entire original string as a Pandoc string
        return text
    end
end

function RemoveBeforeLastTab(text)
    -- Find the position of the last occurrence of '\t'
    local lastTabPos = text:match(".*()\t")

    -- Check if a tab was found
    if lastTabPos then
        -- Return everything after the last '\t' as a Pandoc string
        return text:sub(lastTabPos + 1)
    else
        -- If there are no tabs, return the entire original string as a Pandoc string
        return text
    end
end

--Pandoc filters
if FORMAT:match 'html' then
    function Div(el)
        --normalize div
        el.content = Normalize(el)

        --substitute clause number string with link
        el.content = MultipleClauses(el)
        el.content = Substitute(el, "clause")
        if el.classes[1] ~= "TF" then
            el.content = Substitute(el, "figure")
        end
        if el.classes[1] ~= "TH" then
            el.content = Substitute(el, "table")
        end
        -- if el.classes[1] == "EX" then
        --     if el.content[1] and el.content[1].t == "Str" then
        --         local firstPart = pandoc.List({})
        --         local secondPart = pandoc.List({})
        --         -- check if the tab is in the first element, e.g. "EXAMPLE:\t"
        --         if el.content[1].text:find("EXAMPLE:\t") or el.content[1].text:find("Example:\t") then
        --             firstPart:insert(pandoc.Str("EXAMPLE:"))
        --             secondPart = pandoc.List(el.content)
        --             secondPart[1] = pandoc.Str(RemoveBeforeLastTab(el.content[1].text))
        --             -- the tab is in the third element, e.g. "EXAMPLE 1:\t"
        --         elseif el.content[1].text:find("EXAMPLE") then
        --             secondPart = pandoc.List(el.content)
        --             secondPart:remove(1)
        --             secondPart:remove(1)
        --             firstPart:insert(pandoc.Str("EXAMPLE " .. RemoveAfterFirstTab(secondPart[1].text)))
        --             secondPart[1] = pandoc.Str(RemoveBeforeLastTab(secondPart[1].text))
        --         end
        --         -- Clean up spaces before punctuation in secondPart (inline list)
        --         cleanupSpacesBeforePunctuation(secondPart)
        --         --add two divs, one for the first part and one for the second
        --         local firstDiv = pandoc.Div({pandoc.Plain(firstPart)})
        --         firstDiv.classes = pandoc.List({})
        --         local secondDiv = pandoc.Div({pandoc.Plain(secondPart)})
        --         secondDiv.classes = pandoc.List({})
        --         --set the content of the original div to be the two new divs
        --         el.content = pandoc.List({ firstDiv, secondDiv })
        --     else
        --         -- This is a reference
        --         -- Organize into two columns - one for the tag and one for the citation
        --         if el.content[1] and el.content[1].t == "Span" and el.content[1].content[2] and el.content[1].content[2].t == "Link" and el.content[1].content[2].content[1] and el.content[1].content[2].content[1].text:find("(%[?%s*(i?%.?%d+)%])") then
        --             local reference_tag = el.content[1]
        --             local everything_else = {}

        --             for i = 2, #el.content do
        --                 table.insert(everything_else, el.content[i])
        --             end

        --             el.content = pandoc.List({ reference_tag, pandoc.Span(everything_else) })
        --         end
        --     end
        -- end
        -- if el.classes[1] == "NO" or el.classes[1] == "TAN" then
        --     if el.content[1] and el.content[1].t == "Str" then
        --         local firstPart = pandoc.List({})
        --         local secondPart = pandoc.List({})
        --         -- check if the tab is in the first element, e.g. "NOTE:\t"
        --         if el.content[1].text:find("NOTE:\t") then
        --             firstPart:insert(pandoc.Str("NOTE:"))
        --             secondPart = pandoc.List(el.content)
        --             secondPart[1] = pandoc.Str(RemoveBeforeLastTab(el.content[1].text))
        --             -- the tab is in the third element, e.g. "NOTE 1:\t"
        --         elseif el.content[1].text:find("NOTE") then
        --             secondPart = pandoc.List(el.content)
        --             secondPart:remove(1)
        --             secondPart:remove(1)
        --             firstPart:insert(pandoc.Str("NOTE " .. RemoveAfterFirstTab(secondPart[1].text)))
        --             secondPart[1] = pandoc.Str(RemoveBeforeLastTab(secondPart[1].text))
        --         end
        --         -- Clean up spaces before punctuation in secondPart (inline list)
        --         cleanupSpacesBeforePunctuation(secondPart)
        --         --add two divs, one for the first part and one for the second
        --         local firstDiv = pandoc.Div({pandoc.Plain(firstPart)})
        --         firstDiv.classes = pandoc.List({})
        --         local secondDiv = pandoc.Div({pandoc.Plain(secondPart)})
        --         secondDiv.classes = pandoc.List({})
        --         --set the content of the original div to be the two new divs
        --         el.content = pandoc.List({ firstDiv, secondDiv })
        --     end
        -- end
        el.content = Substitute(el, "annex")
        
        -- Final cleanup: remove spaces before punctuation
        cleanupSpacesBeforePunctuation(el.content)
        
        return el
    end

    function Para(el)
        --normalize Para
        el.content = Normalize(el)
        
        -- Final cleanup: remove spaces before punctuation
        cleanupSpacesBeforePunctuation(el.content)

        el = Linking(el)
        return el
    end

    function Plain(el)
        el = Linking(el)
        return el
    end

    function Strong(el)
        el = Linking(el)
        return el
    end

    function Emph(el)
        el = Linking(el)
        return el
    end

    function Underline(el)
        el = Linking(el)
        return el
    end

    function Span(el)
        el = Linking(el)
        return el
    end

    function Str(el)
        --substitute reference with link
        local startIndex, endIndex, reference, key = el.text:find("(%[?%s*(i?%.?%d+)%])")
        if not key then
            return el --no reference found, return the element as is
        end

        if reference then --reference found
            return pandoc.Span({
                pandoc.Str(el.text:sub(1, startIndex - 1)),
                pandoc.Str(reference),
                pandoc.Str(el.text:sub(endIndex + 1))
            })
        end
    end
end