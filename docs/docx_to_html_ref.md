# Requirements
---

## Command line tools
- Pandoc
- libreoffice (command line)
- mogrify / imagemagick
- 7z

## Python

### Version
3.10.xx

### Packages
Check the requirements.txt file for the needed packages.

# Generate html from docx
---
Move to the right folder:
> `cd docx_to_html`

Create a temp docx and API.css, which contains the rules that API.html will use:  
> `preprocessing.py WORD_DOCUMENT.docx`

### Explanation of preprocessing.py and styles
The biggest challange when trying to convert from docx to html (or vice versa) is to keep in the generated output the style info that Pandoc doesn't take care of.

The general idea is marking down styles in a temporary file (*temp.docx*), and generating a css equivalent for each style. Then another script will do the linking between the strings we marked as styled and the corresponding style in our *API.css*.

---

**The concept of Run:**  
Runs are the building blocks for a Word paragraph. They can contain text, images and mostly style info (like the font used or the color of the text). The only info Pandoc keeps after the conversion is the font weight and shape (bold, italic and/or underline) which are coded as different types of elements in the Pandoc internal tree representation of the document. Pandoc, sadly, doesn't have the concept of Run.
- ***Solution:***  
We mark the start and end of a Run with a special tag `@#!` this way we know exactly when to start applying a certain style and when to stop. The style to be applied to each run is defined by the first word after the tag.
- ***Example:***  
In *temp.docx* we could find something like "@#! HTML_Variable hasPrice @#!" which means
the string "hasPrice" is a run marked with style "HTML_Variable".  

>Note: sometimes Word is silly and considers multiple consecutive strings with the exact same style as multiple runs (this is often an artifact of multiple manipulations on the document), so in *temp.docx* we could find something like a single word where some clusters of letters are marked as a run and the rest as another (but usually with the same style), this doesn't affect the output visually in any way, but it makes a messier HTML (e.g. we have a word that spans multiple html tags). 

---

**Paragraph Styles and Character Styles:**  
Word docx format differentiates between Paragraphs Styles, that are applied to a whole paragraph and can some times drastically change the appearence of a paragraphs, such as "Heading 1" or "Bullet List"; and Charachter styles, that are applied only to a single Run.

- Charachter styles have all the style info a normal run could have, but they're usefule since they can be reused easily
- Paragraphs styles could have info about the font, but usually carry other info about how the paragraph is displayed in the page, such as indentation or spacing.

Both of these styles are marked in the temp.docx file, but since Pandoc actually has an internal representation for paragraphs, marking those is easier, we only need a tag at the start of the paragraph and we know it is applied all the way till its end. The tag used is `[{[--STYLENAME--]}]`.  
- ***Example:***  
"`[{[--EX--]}]` This is a small paragraph." would generate in the HTML a paragraph "This is a small paragraph." with style "EX" applied to it

---
**Ondemand styles:**  
Sometimes in the original document we want to highlight a certain bit of text with some style, like a bigger font or a different color, but we don't create an appropriate Characher or Paragraph style for it. Visually the result is the same, but our script doesn't know how to keep style info without a style.
- ***Solution:***  
We create a custom CSS style, and we mark that text with the new style
- ***Example:***  
"@#! ondemand_CHAR_name_Courier_New Some text @#!", means "Some text" is a run marked with style "ondemand_CHAR_name_Courier_New".  

>Note: the name of the custom style is very descriptive. It always starts with "ondemand", followed by the type "CHAR" or "PARA", followed by what property has beeen changed in this style and what is it's value. In the example the font "name" is "Courier New". Since these are CSS class names they follow the same rules, so there can't be spaces or special characters other then the underscore.

---
**How tabs and space-indentation are preserved:**  
Another challange arose from using Pandoc as a conversion tool is keeping the whitespace charachter as they are in the original document.

For some reason Pandoc collapses all consecutives whitespaces in a single pandoc.Space element (*internal Pandoc representation of the document*), this means that "  \t \t  " is treated in the same way as simply " ", or "\t"; they all become a pandoc.Space object and in the outpt they are rendered as a sigle space " ".  
1. Tabs
    - ***Solution:***  
    To keep the tabs preserved we substitute them with another special tag `{{{{TAB}}}}` this special string then will be replaced again with "\t" so that we get the desired output.
    - ***Example:***  
    "EXAMPLE 1:{{{{TAB}}}}example text" would become "EXAMPLE 1:\texample text" and would be properly rendered.

2. Space-indentation
    - ***Workaround:***  
    Since the need for keeping the space-indentation is presented only in snippets of code, which have style HTML_Sample in the original document, we replace all spaces in runs that have this style with `"\xa0"` Non-Breaking Spaces (unicode U+00A0). These are kept unbothered by Pandoc and we will swap them back with normal spaces in another step.
    - ***Example:***  
    `"somejson" : {`  
    `    "codeWithStyle" : "HTML_sample"`  
    `}`  
    becomes  
    `"somejson"\xa0:\xa0{`  
    `\xa0\xa0\xa0\xa0"codeWithStyle"\xa0:\xa0"HTML_sample"`  
    `}`  

---
**Generated Output:**
- *GENERATED_OUTPUT* : A directory that contains all generated output  
- *temp.docx* : word document with all the marking and substitutions said above
- *API.css* : file with all the ccs rules that imitates the style of the original document's Paragraph styles and Charachter styles, plus our custom Ondemand styles
- *background_hihglight.css* : file that carries additional style info to highlight the background of certain html elements (only used for debugging purposes)

---
Clean up:
> `rm -rf media`

Copy `customCSS.css` to `GENERATED_FILES/API`, created by `preprocessing.py`:
> `cp customCSS.css GENERATED_FILES/API/customCSS.css`

Usa pandoc to extract images:  
> `pandoc --extract-media GENERATED_FILES -f docx -t html -s GENERATED_FILES/temp.docx -o GENERATED_FILES/API.html`

> `cd GENERATED_FILES/media`

Convert all EMF vector images to png, so that HTML can show them:  
> `libreoffice --headless --convert-to png *.emf` 

or 

> `soffice --headless --convert-to png *.emf`

Trim excess background:  
> `mogrify -trim *.png` 

or 

> `magick mogrify -trim *.png`

> `cd ../..`

Finally create API.html, reusing pandoc with our custom filters and toc option:  
> `pandoc --resource-path GENERATED_FILES -f docx -t chunkedhtml -L filter_1.lua -L filter_2.lua  --css=customCSS.css --css=API.css -s GENERATED_FILES/temp.docx -o GENERATED_FILES/API/html_dirty --toc --toc-depth 4 --template=official.html --split-level=1`

### Explanation of Lua scripts  
With the above command we run two lua scripts (called filters in Pandoc terminology). These get executed in order during the convsersion.  
What happens under the hood is something like this:
> starting docx document -> Pandoc creates its internal representation of that document -> Filter 1 is executed on that internal representation -> Filter 2 is executed on that exact instance of Pandoc's internal representation -> HTML is generated

Why do we need these scripts in the middle? We need to clean up all the marking we did in the preprocessing step.

---

**Filter 1:**  
The first filter does most of the job. First of all all string get filtered so that 
`{{{{TAB}}}}` gets replaced by `\t` again, restoring tabs.
Then on each element of the document we call 2 functions:

1. ***Run():*** This function has the purpose of recognizing the structure `@#! CHAR_STYLE some text @#!` that we introduced in the preprocessing step. When such a pattern is recognized insted of the text being passdown as Str (Pandoc element for strings) it gets encapsulated in a Span, so that we can set the attribute `class` to `CHAR_STYLE`. This way css style will be applied correctly

2. ***Style():*** This function has the main purpose of extrapolating the style of the paragraph. If a paragraph has a certain style set, it would be marked with 
`[{[--PARA_STYLE--]}]` at the beginning of the paragraph. Instead of passing this as a Para element (Pandoc version of HTML \<p>), it gets replaced with a Div element, this way we can set via pandoc the `class` attribute to `PARA_STYLE`, applying css style to the element.
    - *Additionally:* an id for images and table headers (marked with `TF` and `TH`) is created, so that we can link them in the second script.

- On Paragraphs we also call:  
    ***Reference():*** This function has the purpose of relating in a table the references patterns `[number]` or `[i.number]` to a link that points to its definition.
- On Images we also:
    - change the extension, so the html properly uses the .png images instead of the unsupported .emf exesnion
    - create a yellow overlay for debugging purposes if the images format was not originally .emf as expected.
- On Headers:  
    Since annex headers all have level 8, we relate in a table, as we did with references, the annex name and their respective link.
---
**Filter 2:**  
This filter finishes the job of the first filter, using the tables we built in previous step and pandoc automatically generated toc links.

*First some clean up:*
>  Sometimes certain portions of text get encapsulated in Plain objects, e.g `"Some text"`, instead of being `[Str("Some"), Space(), Str("text")]` as expected in Pandoc, it's `[Plain(Str("Some")), Plain(Space()), Plain(Str("text"))]`. 
> This causes some problems with the other functions since they expect the first structure, so we use the function ***Normalize()*** to ensure the proper structure is respected in our document.

After normalizing it, we basically run 2 fucntions on each element of the document:
1. ***Substitute(el, word):*** this function has the purpose of replacing every instance of `word` followed by a pattern of type `x.x.x.x` with a link pointing to that specific instance of word. This links are generated via helper functions.  
*Example:* `Substitute(el, clause)` will substitute each pattern of `clause x.x.x.x` with a link generated by **ClauseLink()** function, e.g. `clause 4.4.2` will point to  clase 4.4.2 in the document.  
*word* can be clause, table, figure or annex

2. ***MultipleClauses():*** similarly to Substitute, but it specifically handles multiple `x.x.x.x` patterns after the word `clauses`.
*Example:* in `clauses 4.4.1, 4.4.2, 4.4.3 and 4.4.4` each clause number `x.x.x` will become a link to that clause.

3. Every string of type `[number]` or `[i.number]` will be subtituted with the link pointing to that reference definition.




---

### Explanation of the visual cues of the generated HTML
- grey background: paragraph style applied
- vertical grey bar: HTML blockquote, due to indentation in docx
- text is highlighted: on-demand style, i.e. the text's font is changed wrt to its own paragraph style base font

# Generate docx from html
Copy your manipulated version of ETSI_GS_skeleton.docx to the docx_to_html folder, then generate html_to_docx_output.docx:  
> `html_to_docx.py ./API`

### Explanation of html_to_docx.py

In the reverse step, we want to generate a docx, starting from our html. Using Pandoc we would have some trouble with styles. So we decided to write it manually.  
Basically we use BeautifulSoup4 to parse and navigate the html and in combination with it, we use python-docx (starting from an ETSI Skeleton) in order to write one-by-one the content of each html tag in the docx document.  

---
**Recreate the styles:**  
recreating the style for Ondemand style it's a bit tricky since we don't wont to actually have these styles saved in the word document.
- ***Solution:*** we use cssutils to parse the CSS used for style and create a list of Styles object, these objects just hold the same style properties we passed down from the original docx Document to the generated HTML, and two method that let us apll those properties to a run or paragraph.

---
**The main loop:**  
We iterate each html tag with bs4, and we call over each tag the function `handle_tag()`: this is where most of the magic happens, we call this fucntion recursevly onto each tag's children so we can handle every indivual bit of information as we please.

We have some variables that keep the state of previous iterations, they will be introduced as we proceed into the explanation. The two most important ones are `run` and `para`. They keep the reference to the current paragraph/run that we're working on, they're basically just pointers.

- **Step 1:** identifying the type of tag. We use the `tag.name` property that is basically what's written in the HTML. E.g. the tag `<h1>hello</h1>` will have name `"h1"`. 

- **Step 2:** based of a tag's name we perform different actions.
    - *blockquote*: we just iterate over the children and call the handle_tag function on them.
    - *table:* for table we call a special function `handle_table()`.
    - *headers:* we add the text in a paragraph with style *"HeadingX"* where x is the header's level. **This is basically how headers are handled in docx document, just paragraphs with some style.**
    - *ol/ul:* we first increment the variable `list_level`, that keeps track of the indentation level of everithing we wirte in the list items, we iterate over the childrens and then decrements the list_level variable so that the normal state is restored.
    - *p/div:* for what concerns us paragraphs and divs are basically the same thing, with one exception, divs should always have a *class attribute* with the style we need to apply. We reset `style` variable to **"Normal"** and the `para` reference to **None**. 
        - <u>div:</u> If we find the *class attribute* in the list of document's style, we use that as the value of `style`; if we have a class, but its name is not in the document's style list (this likely means it is an ondemand style), we use our custom Style object as `para_style`.  
        - <u>p:</u> If we have a list level different then 0, we set the `style` to **"Bx"** where x is the value of `list_level` **(as in the heading case, bulletlists are just paragraphs with some specific style)**; if the paragraph has a class (this only happens due to pandoc automatically marking headers with level greater then 6 as paragraphs with class "heading"), we handle that as a special case.

        We call `fix_paragraph()` to remove some unwanted spaces from the start/end of the previous pragraphs (the one we just finished working on). Then we create a new paragraph object and save its reference in `para`; if we have a value for `para_style` we use the `apply_format()` method to  apply that style.  
        We reset `run` to **None** too, so we don't write new text in the runs of previous paragraphs. If we have an *id property* we call the `add_bookmark()` function.

        Finally we loop over the childrens and call `handle_tag()`.

    - *a:* we generate a link, it can be internal (*href property* starts with "#") or external (see explanation of `add_link()` and `add_bookmark()`).
    - *inlines:* inline tags are tags that can be found inside paragraphs and change the appearence of some text, they basically tell us when to start a new run.  
    If `run` is **None** we create a new run and if we have a value for `para_style` we apply that syle. Then we modify this runs properties based on what type of inline we are handling:
        - *br:* simply add "\n" at the end of run's text.
        - *strong/u/em:* apply that style property to this run.
        - *img:* (runs can also contain images) add an image to this run
        - *span:* (this was a run in the orginal document) take its *class property* and apply correspondant style as with divs

    - *NavigableString:* take the text and write it to the current paragraph or run. (this is the lowest level element when parsing with bs4)
---
 **Explanation of handle_table()**  
This function simply tries to replicate the HTML table in the docx document.
1. The first step is to create a table with the right number of rows (just count the \<tr> elements).
2. then we crate the columns with the proper width using the info in the \<colgroup> element.  

Now that we have a nice structure for our table, we iterate over the \<td> or \<th> elements to fill in the content. To do so we keep track of two indexes (i and j) and a variable `cell` that references the current cell (this is needed to create new paragraphs inside of the cell we're working on). For very cell html element that represents a cell we iterate over its children and call `handle_tag()` on them.  

The only special case is when a cell has a spanning attrubute (`rowspan` or `colspan`) in this situation we use the python-docx `merge()`, but our indexes, i and j,s still point to the same cells even if they are visually shown as merged, so in our loop we skip cells till we reach the end of the merged region and we proceed writing down the content of the table. 

---
**Explanation of add_bookmark()**  
This function creates a bookmark (basically the destination addres of an internal link). It basically works by modifying the xml directly, adding two tags `<w:bookmarkStart>` and `<w:bookmarkEnd>` to encapsulate some text. The `w:name` attribute is used to create links that point to this bookmark and the `w:id` is unique in the whole document. To make sure we don't use the same id twice, we simply increment a global counter.

---
**Explanation of add_link()**  
This function basically complements `add_bookmark()` by actually creating hyperlinks elements in the xml and applying to them the right style. It can create both internal or external links. Internal links point to a previously created bookmark, while external links point to a web page.

---
**Explanation of fix_indentation()**  
This function is called while handling a paragraph (\<p> or \<div> elements) when `list_level` is not 0. It basically modify the xml `<w:ilvl>` element's `w:val` property to properly adjust intentation.

---
Invoke postprocessing, and create the final docx, named html_to_docx_output_fixed.docx:
> `postprocessing.py html_to_docx_output.docx ./media`
