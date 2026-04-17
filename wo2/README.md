# 1. Introduction

## 1.1 Setup

### 1.1.1 Required Software

#### [Miniconda](https://docs.conda.io/projects/conda/en/stable/user-guide/install/index.html) or [Pyenv](https://github.com/pyenv/pyenv) or any other python environment manager

Latest

#### [Pandoc](https://pandoc.org/installing.html)

Version 3.7.0.2

#### [LibreOffice (command line)](https://www.libreoffice.org/)

Latest

#### [ImageMagick](https://imagemagick.org/)

Latest

#### [Node.js & Prettier] (https://nodejs.org/) 

```npm install -g prettier```

Latest

### 1.1.2 Optional Software

#### [WSL (Windows Subsystem for Linux)](https://learn.microsoft.com/en-us/windows/wsl/install)

See additional setup steps in [section 1.2.1](#121-for-use-with-wsl).

### 1.1.3 Create a virtual environment

If you prefer to use Minconda or Pyenv, setup a virtual environment according to the following steps. If you are not using Miniconda or Pyenv, you can use any other python environment manger, just go to point 3 of the list and install the requirements using pip.

1. Setup
    1. Follow the [instructions](https://docs.conda.io/projects/conda/en/stable/user-guide/install/index.html) to setup Miniconda, OR...
    2. Follow steps [A](https://github.com/pyenv/pyenv?tab=readme-ov-file#a-getting-pyenv), [B](https://github.com/pyenv/pyenv?tab=readme-ov-file#b-set-up-your-shell-environment-for-pyenv), [C](https://github.com/pyenv/pyenv?tab=readme-ov-file#c-restart-your-shell), and [D](https://github.com/pyenv/pyenv?tab=readme-ov-file#d-install-python-build-dependencies) of the [instructions](https://github.com/pyenv/pyenv?tab=readme-ov-file#installation) to setup Pyenv.

2. Create a virtual environment with Python version **3.10.16** to use with the script.

   1. For Miniconda...
       1. `conda create --name environment_name python=3.10.16`
       2. `conda activate environment_name`

    2. For Pyenv...
        1. `cd path/to/ETSI_GS_CIM_009`
        2. `pyenv install 3.10.16`
        3. `pyenv local 3.10.16` - Use Python 3.10.16 with this folder
        4. `pyenv virtualenv environment_name`
        5. `pyenv activate environment_name`

3. Install the requirements contained in _requirements.txt_.
   1. `cd path/to/ETSI-GS-CIM-009`
   2. `pip install -r requirements.txt`

### 1.1.4 Check Pandoc

Ensure Pandoc version **3.7.0.2** is installed.

`pandoc --version`

## 1.2 For Use with WSL

To ensure the script runs correctly with WSL 1[^1], do one of the following...

- Ensure the directory containing the script's files is saved in the Linux filesystem (ex., at `\\wsl$\{Distro}\home\{user}\path\to\script\dir`).

  **OR**

- Ensure the current user has full control of the directory containing the script's files within the base Windows filesystem (ex., at `C:\path\to\script\dir`).
    1. Right click on the top-level directory in the file explorer.
    2. Click *Properties*
    3. Go to the *Security* tab
    4. Click *Edit* to modify permissions.
    5. In the list, select the current user.
       
       If the current user is not in the list, click *Add*. In the dialogue that opens, ensure that the *User* object type is selected and type the current user's username in the *Enter object names to select* box. Click *Check names*, then click *OK*.
    
    6. Under *Permissions*, check the box for *Full control*, then click *Apply* and *OK*.

## 1.3 Expected Folder Structure after conversion

Through conversion you will eventually end up with the following folder structure:

```
Current folder
└── GENERATED_FILES
    └── {folder_name}
        ├── docx
        ├── html
        |   └── media
        ├── md
            └── media
        ├── customCSS.css
        ├── ETSIstyles.css
```

Where:

- `{folder_name}` is the name of the folder you specified when running the `init.py` script.
- md is the folder containing the Markdown files where you will work
  - html/media is the folder containing the media files (images) referenced in the Markdown files
- customCSS.css is the CSS file used for custom style used for the HTML pages only. **This file is volatile, and is copied to the output directory during conversion.**
- ETSIstyles.css is the CSS file used to represent styles coming out of a Word ETSI document. **This file is also volatile, and is copied to the output directory during conversion.**
- html is generated from the Markdown files. **This folder is automatically created during conversion.**
  - html/media is the folder containing the media files (images) referenced in the HTML files. **This folder is automatically created during conversion.**
- docx is generated from the HTML files. **This folder is automatically created during conversion.**

# 2. Usage

The script `convert.py` handles the following conversions:

| From       | To         |
| ---------- | ---------- |
| Dirty HTML | Markdown   |
| Markdown   | Clean HTML |
| Clean HTML | Docx       |

## 2.1 Arguments

`convert.py -h` - List the script's arguments

### 2.1.1 Required

- `--frm [file type]` - Source Types: **html_dirty** for HTML to run additional processing on to produce desired formatting, **html** for HTML that is already properly formatted, or **md** for Markdown

- `--to` - Destination Types: **html**, **md**, or **docx** It must be different from the source file type provided with `--frm`.

- `--folder` - The name of the folder within _ETSI-GS-CIM-009/GENERATED_FILES_ to place the converted files
  - BEST PRACTICE: Use a short term by which the document can be uniquely identified, for example, _API_ or _primer_.

### 2.1.2 Optional

- `--src` - Provide the path of the source directory rather than allowing the script to generate it.
  - If this argument is not provided, the source path will be _ETSI-GS-CIM-009_/_GENERATED_FILES_/_{value provided via `--folder`}_/_{value provided via `--frm`}_.

- `--file_order` - Provide the path to a JSON that contains the order in which user-created clauses and annexes should be.
    - If this argument is not provided, the default ordering convention will be used. See [section 2.2.1.1](#2211---preparation-create-markdown-from-scratch) for more details.

## 2.2  Conversion

`convert.py` is a script that handles the conversion of documents between different formats. It can be used to convert Markdown files to HTML, HTML files to Docx, and "dirty" HTML files to "clean" Markdown (when one wants to start a new document from some content in a DOCX file).

### 2.2.0 General Usage (Markdown to HTML to DOCX)

It follows the general usage pattern:

**From md to html (validation of Markdown):**

`convert.py --frm md --to html --folder {folder_name} --src relative/or/absolute/source/path`

**NOTE**: The `--src` argument is optional and can be used to specify the source directory when the Markdown files are located in a different directory (e.g. a dedicated repository or workspace). When provided, it will use it to locate the md files. This shall point to the directory containing the Markdown files and the media folder.

**NOTE 2**: If `--src` is omitted, the script will expect to find a "md" folder in the "./GENERATED_FILES/<folder_name>" path containing the Markdown files and the media folder.


**From html to docx (generation of DOCX):**

`convert.py --frm html --to docx --folder {folder_name}`


### 2.2.1 Starting from scratch or existing DOCX to Markdown

Run the following command to create the necessary folder structure:

```bash
python init.py --folder {folder_name}
```

This will generate the folder structure required for the conversion process.

From now on, either of the following two paths can be taken:
- Create Markdown files from scratch, see [section 2.2.1.1](#2211---create-markdown-from-scratch)
- Convert an existing DOCX file to Markdown, see [section 2.2.1.2](#2212---convert-docx-to-markdown)

In both cases, you will end up with markdown files in *GENERATED_FILES*/*{folder_name}*/*md*. Then proceed to [section 2.2.2](#222---dirty-html-to-markdown) to convert the "dirty" HTML to "clean" Markdown.

#### 2.2.1.1   Create Markdown from scratch

1. If it does not already exist, create the directory *GENERATED_FILES*/*{folder_name}*/*md* where `convert.py` is by running the init script.
2. Copy template files of [Required Markdown files](./templates/document_skeleton/)
3. Decide whether to use the script's default naming convention or custom clause and annex names.
    - Default: Name clauses *clause-{number 4-20}* and annexes *annex-{letter a-z}*. Clauses and annexes will be arranged in order according to the alphanumeric suffix.
    - Custom: Create a file ordering JSON according to the [template](./templates/json/file_order.json) and provide it to the script with the `--file_order` argument.
    - In either case, if any other files that follow the naming convention *clause-{some text}* or *annex-{some text}* will be ordered alphabetically after the predefined files in the appropriate section of the document.
4. Create a *media* directory inside the directory created in step 1.
    - As images are added to the Markdown, place the image in `PNG` and `EMF` form inside.[^2]

At this point, the document's clauses and annexes can be created. It is important to follow the following considerations to ensure the document is created properly:
- Ensure any files defined in a [file ordering JSON](./templates/json/file_order.json) are present in the source directory created in step 1, otherwise the script will print an error and quit prematurely.
- Ensure that the [required files](./templates/document_skeleton/) are all present in the source directory, otherwise the script will print an error and quit prematurely.

#### 2.2.1.2   Generate "dirty" HTML

##### 1) Preprocess *{folder_name}.docx*

`preprocessing.py {folder_name}.docx`

##### 2) Copy *customCSS.css* to the document's directory

`cp customCSS.css GENERATED_FILES/{folder_name}/customCSS.css`

##### 3) Prepare the images in *{folder_name}.docx* for the HTML

1. `pandoc --extract-media GENERATED_FILES/{folder_name}/temp -f docx -t html GENERATED_FILES/{folder_name}/temp/temp.docx -o GENERATED_FILES/{folder_name}/temp/{folder_name}.html`

2. `libreoffice --headless --convert-to png --outdir GENERATED_FILES/{folder_name}/temp/media GENERATED_FILES/{folder_name}/temp/media/*.emf`

3. Either of the following...
   - `mogrify -trim GENERATED_FILES/{folder_name}/temp/media/*.png`
   - `magick mogrify -trim GENERATED_FILES/{folder_name}/temp/media/*.png`

#### Convert to HTML using Pandoc

`pandoc --resource-path GENERATED_FILES/{folder_name}/temp -f docx -t chunkedhtml -L filter_1.lua -L filter_2.lua --css=customCSS.css --css="{folder_name}.css" -s GENERATED_FILES/{folder_name}/temp/temp.docx -o GENERATED_FILES/{folder_name}/html_dirty --toc --toc-depth 4 --template=official.html --split-level=1`

#### Delete temporary files that are no longer needed

`rm -r GENERATED_FILES/{folder_name}/temp`

#### Generate Markdown from the "dirty" HTML

Starting with "dirty" HTML contained in the default source location (that is, _GENERATED_FILES_/_{folder_name}_/_html_dirty_), convert to "clean" Markdown, which will be contained in _GENERATED_FILES_/_{folder_name}_/_md_.

`convert.py --frm html_dirty --to md --folder {folder_name}`

Specify a different directory containing the "dirty" HTML files.

`convert.py --frm html_dirty --to md --folder {folder_name} --src relative/or/absolute/source/path`

### 2.2.2 Markdown to HTML

---

Starting with Markdown files contained in the default source location (_GENERATED_FILES_/_{folder_name}_/_md_), convert to HTML. The Markdown is assumed to be in a "clean" state.

`convert.py --frm md --to html --folder {folder_name}`

Specify a different directory containing the Markdown files.

`convert.py --frm md --to html --folder {folder_name} --src relative/or/absolute/source/path`

Creates a diff version of the HTML by comparing it with `./GENERATED_FILES/{folder_name}-base`.
When using `--diff`, `--src` is required.

`convert.py --frm md --to html --folder {folder_name} --src relative/or/absolute/source/path --diff`

Creates a diff version of the HTML comparing it with a branch or a commit ID specified in `{target_name}`. If not specified, uses `main` or `master`.
When using `--diff-git`, `--diff` is not necessary, if both are present `--diff` will be ignored.

`convert.py --frm md --to html --folder {folder_name} --src relative/or/absolute/source/path --diff-git {target_name}`

By default, the generated file requires a web server (e.g., Live Server - a VS Code extension). To generate a diff that can be opened without a web server, use the `--no_lazy_toc` command.

`convert.py --frm md --to html --folder {folder_name} --src relative/or/absolute/source/path --diff --no_lazy_toc`

### 2.2.3 HTML to Docx

---

Starting with HTML files contained in the default source location (_GENERATED_FILES_/_{folder_name}_/_html_), convert to Docx.

`convert.py --frm html --to docx --folder {folder_name}`

[^1]: These steps may not be necessary with WSL 2, but it is recommended to follow them nevertheless.

[^2]: Method subject to change

# 3. Usage with Docker

## 3.1 Requirements

Install Docker on your local machine. The script will automatically build the Docker image and mount the necessary paths as required.

## 3.2 Run
To run the conversion with Docker, use the shell script appropriate for your operating system.

The accepted parameters are the same as those explained in [section 2.2](#22--conversion).

**For Mac/Linux:**

`bash convert.sh --parameters [--arch amd64|arm64] [--rebuild]`

**For Windows:**

`./convert.bat --parameters [--arch amd64|arm64] [--rebuild]`

Where `--parameters` are the same as those explained in [section 2.2](#22--conversion), `--arch` is an optional parameter and specifies the Docker architecture (default `amd64`), and `--rebuild` forces a rebuild of the Docker image. 

# 4 Other tools

## 4.1 Cleanup

The cleanup_md.py script is a versatile tool designed to refine and validate Markdown files at any stage of their lifecycle. While the DOCX to MD conversion is standardized, running this script is highly recommended before converting Markdown to HTML to ensure the structural integrity of the source.

It achieves this through operations such as validating that code blocks are correctly matched, converting grid tables into standard Markdown, automatically indenting and validating JSON code blocks, and standardizing the document blocks. It also applies prettier for better readability.

(Linux/Mac users)
`bash cleanup_md.sh --src {path/to/folder} [--arch amd64|arm64] [--rebuild]`
`python cleanup_md.py --src {path/to/folder}`

(Windows)
`./cleanup_md.bat --src {path/to/folder} [--arch amd64|arm64] [--rebuild]`

`--src` is required: it specifies the source directory or a single file.
`--arch` optional: this parameter defines the target CPU architecture for the Docker image.
`--rebuild` optional: this parameter forces Docker to re-build the image from the Docker file.
`--help` optional: this parameter displays the available commands in the terminal.

## 4.2 DOCX to MD

The main scripts docx_to_md.sh (Linux/Mac) and docx_to_md.bat (Windows) automate the transition from Word (.docx) to Markdown (.md).

(Linux/Mac users)
`bash docx_to_md.sh --file {path/to/file.docx} [--start-from <step>] [--arch amd64|arm64] [--rebuild] [--docker]`

(Windows)
`./docx_to_md.bat --file {path/to/file.docx} [--start-from <step>] [--arch amd64|arm64] [--rebuild]`

`--file` is required: this parameter specifies the source directory of the file you wish to convert.
`--start-from` optional: this parameter allows you to start the conversion from a specific step
`--arch` optional: this parameter defines the target CPU architecture for the Docker image.
`--rebuild` optional: this parameter forces Docker to re-build the image from the Docker file.
`--help` optional: this parameter displays the available commands in the terminal.
`--docker` optional: this parameter (Linux/Mac only) allows you to run the script using a Docker image


# 5. Debug

## 5.1 Show time reports

Using the `--time` parameter prints the duration of each operation; it is useful for debugging performance.