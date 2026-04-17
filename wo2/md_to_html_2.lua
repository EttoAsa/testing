--THIS LUA FILTER MUST BE APPLIED TO PANDOC IN THE CORRECT ORDER
local debug = false
local pandoc = require "pandoc"


--generates link for caluses
function ClauseLink(text, number)
    text = text:gsub("%-", "‑") --always use non-breaking hyphens for links
    -- find the first . or set the length to the whole string if there is no .
    local first_dot = number:find("%.") or (#number + 1)
    leading_characters = number:sub(1, first_dot - 1)
    first_character = leading_characters:sub(1, 1)
    if first_character:match("%a") then
        number = first_character:upper() .. number:sub(2)
        return pandoc.Link(text, "annex-" .. first_character:lower() .. ".html#" .. number)
    else
        return pandoc.Link(text, "clause-" .. leading_characters .. ".html#" .. number)
    end
end

--generates link for figures
function FigureLink(text, number)
    text = text:gsub("%-", "‑") --always use non-breaking hyphens for links
    -- find the first .
    local first_dot = number:find("%.") or (#number + 1)
    leading_characters = number:sub(1, first_dot - 1)
    first_character = leading_characters:sub(1, 1)
    -- check if it is a letter
    if first_character:match("%a") then
        return pandoc.Link(text, "annex-" .. first_character:lower() .. ".html#Figure_" .. number)
    else
        return pandoc.Link(text, "clause-" .. leading_characters .. ".html#Figure_" .. number)
    end
end

--generates link for tables
function TableLink(text, number)
    text = text:gsub("%-", "‑") --always use non-breaking hyphens for links
    -- find the first .
    local first_dot = number:find("%.") or (#number + 1)
    leading_characters = number:sub(1, first_dot - 1)
    first_character = leading_characters:sub(1, 1)
    -- check if it is a letter
    if first_character:match("%a") then
        return pandoc.Link(text, "annex-" .. first_character:lower() .. ".html#Table_" .. number)
    else
        return pandoc.Link(text, "clause-" .. leading_characters .. ".html#Table_" .. number)
    end
end

--generates link for annexes
function AnnexLink(text, number)
    text = text:gsub("%-", "‑") --always use non-breaking hyphens for links
    first_character = number:sub(1, 1)
    -- if first character is a letter and it is lowercase, make it uppercase and replace the number
    if first_character:match("%a") and first_character == first_character:lower() then
        number = first_character:upper() .. number:sub(2)
    end
    return pandoc.Link(text, "annex-" .. first_character:lower() .. ".html#" .. number)
end

--helper function that uses the generated toc to link clauses and figures to the respetive header
function Substitute(el, word)
    local newContent = pandoc.List({})
    local pattern = "(%w*%.?%d*%.?%d*%.?%d*%.?%d*%.?%d*%.?%d+%-?%d*)"
    local annexPattern = "(%a%.?%d*%.?%d*%.?%d*%.?%d*%.?%d*%.?%d*)"

    local i = 1
    while el.content[i] do
        local elem = el.content[i]
        if elem.t == "Str" and elem.text:lower():find(word) and not elem.text:find("+++") then --check the next strings to see if we need to link it
            local wordStartIndex = elem.text:lower():find(word)
            local precedentChar = elem.text:sub(wordStartIndex - 1, wordStartIndex - 1)
            local textWithoutWord = elem.text:sub(wordStartIndex + #word)
            local startIndex, endIndex, number = textWithoutWord:gsub("‑", "-"):find(pattern) --check if number is in the same Str elem
            if not number then
                startIndex, endIndex, number = textWithoutWord:gsub("‑", "-"):find(annexPattern) --check if number is in the same Str elem
                if number and elem.text:sub(1, 1):match("%a") and elem.text:sub(2,2):match("%a") then
                    --this is not a clause number, it is something else
                    number = nil
                end
            end
            if not precedentChar:match("~") then
                if number then --create link
                    first_character = number:sub(1, 1)
                    newContent:insert(pandoc.Link(elem.text:sub(1, endIndex), "clause-" .. first_character .. ".html#" .. number))
                    if endIndex < #elem.text then -- if something remains (like a comma or a bracket), append it too
                        newContent:insert(pandoc.Str(elem.text:sub(endIndex + 1, -1)))
                    end
                    goto continue
                end
                -- this may trigger a multiple clause link
                local succ = el.content[i + 2] --next string if it exists should be number
                if succ and succ.t == "Str" then
                    number = succ.text:gsub("‑", "-"):match(pattern)
                    if not number then
                        number = succ.text:gsub("‑", "-"):match(annexPattern)
                        if number and succ.text:sub(1, 1):match("%a") and succ.text:sub(2,2):match("%a") then
                            --this is not a clause number, it is something else
                            number = nil
                        end
                    end
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
                                local lastNumberChar = number:sub(-1)
                                if lastNumberChar == "." or lastNumberChar == "," then
                                    number = number:sub(1, -2) --remove the last char if it is a dot or comma
                                end
                                newContent:insert(AnnexLink(elem.text .. " " .. number, number))
                                if lastNumberChar == "." or lastNumberChar == "," then
                                    newContent:insert(pandoc.Str(lastNumberChar)) --reinsert the dot or comma if it was there
                                end
                            else
                                if debug then print("Unkown behavior for " .. word .. " or link does not exists") end
                            end
                            if debug then print(succ.text, number) end
                            local text, substitutions = succ.text:gsub("‑", "-") --if we substituted we need to account for this, because nbh is not acii anf thus is more then one byte
                            local startIndex, endIndex = text:find(pattern)
                            if not startIndex then
                                startIndex, endIndex = text:find(annexPattern)
                            end
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
        end
        --append the other elements normally
        newContent:insert(elem)
        ::continue::
        i = i + 1
    end
    return newContent
end

function MultipleClauses(el)
    local newContent = pandoc.List({})
    local pattern = "(%w*%.?%d*%.?%d*%.?%d*%.?%d*%.?%d*%.?%d+)"
    local annexPattern = "(%a%.?%d*%.?%d*%.?%d*%.?%d*%.?%d*%.?%d*)"
    local clausesFound = false --this is true when we found the word "clauses" and remain true until we habe clauses numbers following

    local i = 1
    while el.content[i] do
        local elem = el.content[i]

        if elem.t == "Str" then
            --this may be the start of a list of multiple clauses
            if elem.text:lower():find("clauses") then
                local wordStartIndex = elem.text:lower():find("clauses")
                local precedentChar = elem.text:sub(wordStartIndex - 1, wordStartIndex - 1)
                if precedentChar:match("~") then
                    --this is a negated clauses, do nothing
                    newContent:insert(elem)
                    goto continue
                end
                clausesFound = true
                -- Replace plain "clauses" text with a span containing it
                local clausesSpan = pandoc.Span({pandoc.Str(elem.text)})
                clausesSpan.classes = pandoc.List({"clauses-marker"})
                newContent:insert(clausesSpan)
                goto continue
            end

            if clausesFound then
                --check if we found a clause number
                local startIndex, endIndex, number = elem.text:find(pattern)
                if number == nil then
                    --check if it is an annex clause number
                    startIndex, endIndex, number = elem.text:find(annexPattern)
                    if number and elem.text:sub(1, 1):match("%a") and elem.text:sub(2,2):match("%a") then
                        --this is not a clause number, it is something else
                        number = nil
                    end
                end

                if elem.text:match("^,$") or elem.text:match("and") then
                    --this is just a comma or the word 'and' separating the clauses
                    --do nothing
                elseif number then
                    -- we did in fact find a clause number
                    --substitute with linkS
                    -- if first letter is a letter it is an annex
                    if elem.text:sub(1, 1):match("%a") then
                        newContent:insert(AnnexLink(elem.text:sub(startIndex, endIndex), number))
                    else
                        newContent:insert(ClauseLink(elem.text:sub(startIndex, endIndex), number))
                    end
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
        return el.content
    end
    return newContent
end

function Linking(el)
    --substitute clause number string with link
    el.content = MultipleClauses(el)
    el.content = Substitute(el, "clause")
    el.content = Substitute(el, "figure")
    el.content = Substitute(el, "table")
    el.content = Substitute(el, "annex")
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
        if el.classes[1] == "EX" then
            if el.content[1] and el.content[1].t == "Str" then
                local firstPart = pandoc.List({})
                local secondPart = pandoc.List({})
                -- check if the tab is in the first element, e.g. "EXAMPLE:\t"
                if el.content[1].text:find("EXAMPLE:\t") or el.content[1].text:find("Example:\t") then
                    firstPart:insert(pandoc.Str("EXAMPLE:"))
                    secondPart = pandoc.List(el.content)
                    secondPart[1] = pandoc.Str(RemoveBeforeLastTab(el.content[1].text))
                    -- the tab is in the third element, e.g. "EXAMPLE 1:\t"
                elseif el.content[1].text:find("EXAMPLE") then
                    secondPart = pandoc.List(el.content)
                    secondPart:remove(1)
                    secondPart:remove(1)
                    firstPart:insert(pandoc.Str("EXAMPLE " .. RemoveAfterFirstTab(secondPart[1].text)))
                    secondPart[1] = pandoc.Str(RemoveBeforeLastTab(secondPart[1].text))
                end
                --add two divs, one for the first part and one for the second
                local firstDiv = pandoc.Div(firstPart)
                firstDiv.classes = pandoc.List({})
                local secondDiv = pandoc.Div(secondPart)
                secondDiv.classes = pandoc.List({})
                --set the content of the original div to be the two new divs
                el.content = pandoc.List({ firstDiv, secondDiv })
            else
                -- This is a reference
                -- Organize into two columns - one for the tag and one for the citation
                if el.content[1] and el.content[1].t == "Span" and el.content[1].content[2] and el.content[1].content[2].t == "Link" and el.content[1].content[2].content[1] and el.content[1].content[2].content[1].text:find("(%[?%s*(i?%.?%d+)%])") then
                    local reference_tag = el.content[1]
                    local everything_else = {}

                    for i = 2, #el.content do
                        table.insert(everything_else, el.content[i])
                    end

                    el.content = pandoc.List({ reference_tag, pandoc.Span(everything_else) })
                end
            end
        end
        if el.classes[1] == "NO" or el.classes[1] == "TAN" then
            if el.content[1] and el.content[1].t == "Str" then
                local firstPart = pandoc.List({})
                local secondPart = pandoc.List({})
                -- check if the tab is in the first element, e.g. "NOTE:\t"
                if el.content[1].text:find("NOTE:\t") then
                    firstPart:insert(pandoc.Str("NOTE:"))
                    secondPart = pandoc.List(el.content)
                    secondPart[1] = pandoc.Str(RemoveBeforeLastTab(el.content[1].text))
                    -- the tab is in the third element, e.g. "NOTE 1:\t"
                elseif el.content[1].text:find("NOTE") then
                    secondPart = pandoc.List(el.content)
                    secondPart:remove(1)
                    secondPart:remove(1)
                    firstPart:insert(pandoc.Str("NOTE " .. RemoveAfterFirstTab(secondPart[1].text)))
                    secondPart[1] = pandoc.Str(RemoveBeforeLastTab(secondPart[1].text))
                end
                --add two divs, one for the first part and one for the second
                local firstDiv = pandoc.Div(firstPart)
                firstDiv.classes = pandoc.List({})
                local secondDiv = pandoc.Div(secondPart)
                secondDiv.classes = pandoc.List({})
                --set the content of the original div to be the two new divs
                el.content = pandoc.List({ firstDiv, secondDiv })
            end
        end
        el.content = Substitute(el, "annex")
        return el
    end

    function Para(el)
        --normalize Para
        el.content = Normalize(el)

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
end
