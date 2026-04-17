#!/bin/bash

# Script to run docker conversion with parameters
ARCH="amd64"
REBUILD=false
DOCKER=false

# Parse --arch first if present
for arg in "$@"; do
    if [[ "$arg" == "--arch" ]]; then
        ARCH_FOUND=true
    elif [[ "$ARCH_FOUND" == "true" ]]; then
        ARCH="$arg"
        ARCH_FOUND=false
    fi
    if [[ "$arg" == "--rebuild" ]]; then
        REBUILD=true
    fi
    if [[ "$arg" == "--docker" ]]; then
        DOCKER=true
    fi
done

# Validate arch parameter
if [[ "$DOCKER" == true ]] && [[ "$ARCH" != "amd64" && "$ARCH" != "arm64" ]]; then
    echo "Error: --arch must be either 'amd64' or 'arm64'"
    exit 1
fi


# Check if image exists and rebuild if needed
if [[ "$DOCKER" == true ]] && ( ! docker image inspect md-converter &>/dev/null || [[ "$REBUILD" == true ]]); then
  docker build --build-arg TARGETARCH="$ARCH" -t md-converter .
fi

FILE=""
START_FROM=1

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --file) FILE="$2"; shift ;;
        --arch) shift ;; # Already processed in initial loop; consume its value
        --rebuild) ;; # Already processed
        --docker) ;; # Already processed
        --start-from)
            if [[ -n "$2" && "$2" =~ ^[1-9]$|^10$ ]]; then
                START_FROM="$2"
                shift
            else
                echo "Error: --start-from must be followed by a number between 1 and 10"
                exit 1
            fi
            ;;
        --help)
            echo "Usage: $0 [--arch <amd64|arm64>] [--rebuild] --file <file_name>"
            echo ""
            echo "Options:"
            echo "  --file <file_name>      Name of the DOCX file to process (required)"
            echo "  --start-from <step>     Step number to start from (1-10, default: 1)"
            echo "  --docker                Run the conversion inside a Docker container"
            echo "  --arch <amd64|arm64>    Specify the architecture for the Docker image (default: amd64, works only if --docker is used)"
            echo "  --rebuild               Force rebuild of the Docker image (Works only if --docker is used)"
            echo "  --help                  Show this help message and exit"
            exit 0
            ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

# Validate required --file argument
if [[ -z "$FILE" ]]; then
    echo "Error: --file <file_name> is required"
    echo "Use --help to see usage."
    exit 1
fi
DOCX_FILE="${FILE}"
DOCX_BASENAME="$(basename "$DOCX_FILE" .docx)"
FOLDER_NAME="${FILE%.docx}"
GENERATED_DIR="GENERATED_FILES/${DOCX_BASENAME}"
TEMP_DIR="${GENERATED_DIR}/temp"
HTML_DIRTY_DIR="${GENERATED_DIR}/html_dirty"
MD_DIR="${GENERATED_DIR}/md"

echo "============================================================================"
echo "Starting DOCX to MD conversion for: $DOCX_FILE"
if [ "$START_FROM" -gt 1 ]; then
    echo "(Skipping to step $START_FROM)"
fi
echo "============================================================================"

# Check if DOCX file exists (only if starting from step 1)
if [ "$START_FROM" -le 1 ] && [ ! -f "$DOCX_FILE" ]; then
    echo "Error: File $DOCX_FILE not found!"
    echo "Please make sure the DOCX file is in the current directory."
    exit 1
fi

if [ "$START_FROM" -le 1 ]; then
echo ""
echo "[Step 1/10] Cleaning up previous temporary files..."
if [ -d "$TEMP_DIR" ]; then
    rm -rf "$TEMP_DIR"
    if [ $? -ne 0 ]; then
        echo "Warning: Failed to delete temp directory, continuing..."
    fi
fi
fi

if [ "$START_FROM" -le 2 ]; then
echo ""
echo "[Step 2/10] Preprocessing DOCX file..."
if [ "$DOCKER" == true ]; then
    RUN_ARGS=(
      docker run --rm
      --user "$(id -u):$(id -g)"
      -v "$(pwd)":/app:rw
            md-converter src/docx_to_md/preprocessing.py "$DOCX_FILE"
    )
    "${RUN_ARGS[@]}"
else
    python src/docx_to_md/preprocessing.py "$DOCX_FILE"
fi
if [ $? -ne 0 ]; then
    echo "Error: preprocessing.py failed!"
    exit 1
fi
fi

if [ "$START_FROM" -le 3 ]; then
echo ""
echo "[Step 3/10] Copying CSS files..."
echo "./$GENERATED_DIR/customCSS.css"
cp -f ./customCSS.css "./$GENERATED_DIR/customCSS.css"
if [ $? -ne 0 ]; then
    echo "Error: Failed to copy customCSS.css!"
    exit 1
fi
fi

if [ "$START_FROM" -le 4 ]; then
echo ""
echo "[Step 4/10] Extracting media from DOCX..."
if [ "$DOCKER" == true ]; then
    RUN_ARGS=(
      docker run --rm
      --user "$(id -u):$(id -g)"
      -v "$(pwd)":/app:rw
            --entrypoint pandoc
            md-converter --extract-media "$TEMP_DIR" -f docx -t html "${TEMP_DIR}/temp.docx" -o "${TEMP_DIR}/${DOCX_BASENAME}.html"
    )
    "${RUN_ARGS[@]}"
    if [ $? -ne 0 ]; then
        echo "Error: Pandoc media extraction failed!"
        exit 1
    fi
else
    pandoc --extract-media "$TEMP_DIR" -f docx -t html "${TEMP_DIR}/temp.docx" -o "${TEMP_DIR}/${DOCX_BASENAME}.html"
    if [ $? -ne 0 ]; then
        echo "Error: Pandoc media extraction failed!"
        exit 1
    fi
fi
fi

if [ "$START_FROM" -le 5 ]; then
echo ""
echo "[Step 5/10] Converting EMF images to PNG (LibreOffice)..."
if ls "${TEMP_DIR}/media"/*.emf 1> /dev/null 2>&1; then
    if [ "$DOCKER" == true ]; then
        RUN_ARGS=(
          docker run --rm
          --user "$(id -u):$(id -g)"
          -e HOME=/tmp
          -v "$(pwd)":/app:rw
                    --entrypoint sh
                    md-converter -c "if command -v libreoffice &> /dev/null; then libreoffice --headless \"-env:UserInstallation=file:///tmp/libo\" --convert-to png --outdir ${TEMP_DIR}/media ${TEMP_DIR}/media/*.emf; elif command -v soffice &> /dev/null; then soffice --headless \"-env:UserInstallation=file:///tmp/libo\" --convert-to png --outdir ${TEMP_DIR}/media ${TEMP_DIR}/media/*.emf; else echo 'Warning: LibreOffice/soffice not found, skipping EMF conversion...'; fi"
        )
        "${RUN_ARGS[@]}"
        if [ $? -ne 0 ]; then
        echo "Error: LibreOffice conversion failed in Docker!"
        exit 1
        fi
    else
      # Try libreoffice command first, then soffice
      if command -v libreoffice &> /dev/null; then
          libreoffice --headless --convert-to png --outdir "${TEMP_DIR}/media" "${TEMP_DIR}/media"/*.emf
      elif command -v soffice &> /dev/null; then
          soffice --headless --convert-to png --outdir "${TEMP_DIR}/media" "${TEMP_DIR}/media"/*.emf
      else
          echo "Warning: LibreOffice/soffice not found, skipping EMF conversion..."
      fi
      if [ $? -ne 0 ]; then
          echo "Warning: LibreOffice conversion had issues, continuing..."
      fi
    fi
else
    echo "No EMF files found, skipping conversion..."
fi
fi

if [ "$START_FROM" -le 6 ]; then
echo ""
echo "[Step 6/10] Trimming PNG images (ImageMagick)..."
if ls "${TEMP_DIR}/media"/*.png 1> /dev/null 2>&1; then
    if [ "$DOCKER" == true ]; then
        RUN_ARGS=(
          docker run --rm
          --user "$(id -u):$(id -g)"
          -v "$(pwd)":/app:rw
                    --entrypoint sh
                    md-converter -c "if command -v mogrify &> /dev/null; then mogrify -trim ${TEMP_DIR}/media/*.png; elif command -v magick &> /dev/null; then magick mogrify -trim ${TEMP_DIR}/media/*.png; else echo 'Warning: ImageMagick not found, skipping trim...'; fi"
        )
        "${RUN_ARGS[@]}"
        if [ $? -ne 0 ]; then
        echo "Error: ImageMagick trim failed in Docker!"
        exit 1
        fi
    else
      # Try mogrify command first, then magick mogrify
      if command -v mogrify &> /dev/null; then
          mogrify -trim "${TEMP_DIR}/media"/*.png
      elif command -v magick &> /dev/null; then
          magick mogrify -trim "${TEMP_DIR}/media"/*.png
      else
          echo "Warning: ImageMagick not found, skipping trim..."
      fi
      if [ $? -ne 0 ]; then
          echo "Warning: ImageMagick trim had issues, continuing..."
      fi
    fi
else
    echo "No PNG files found, skipping trim..."
fi
fi

if [ "$START_FROM" -le 7 ]; then
echo ""
echo "[Step 7/10] Converting DOCX to HTML with Pandoc..."
# Remove html_dirty directory if it exists to avoid Pandoc errors
if [ -d "$HTML_DIRTY_DIR" ]; then
    echo "Removing existing html_dirty directory..."
    rm -rf "$HTML_DIRTY_DIR"
fi
if [ "$DOCKER" == true ]; then
    RUN_ARGS=(
      docker run --rm
      --user "$(id -u):$(id -g)"
      -v "$(pwd)":/app:rw
            --entrypoint pandoc
            md-converter --resource-path "${TEMP_DIR}" -f docx -t chunkedhtml -L src/docx_to_md/docx_to_html_styling.lua -L src/docx_to_md/docx_to_html_links.lua --css=/app/customCSS.css --css=/app/"${DOCX_BASENAME}.css" -s "$TEMP_DIR/temp.docx" -o "$HTML_DIRTY_DIR" --toc --toc-depth 4 --template=official.html --split-level=1
    )
    "${RUN_ARGS[@]}"
else
  pandoc --resource-path "${TEMP_DIR}" -f docx -t chunkedhtml -L src/docx_to_md/docx_to_html_styling.lua -L src/docx_to_md/docx_to_html_links.lua --css=customCSS.css --css="${DOCX_BASENAME}.css" -s "${TEMP_DIR}/temp.docx" -o "$HTML_DIRTY_DIR" --toc --toc-depth 4 --template=official.html --split-level=1
fi
if [ $? -ne 0 ]; then
    echo "Error: Pandoc HTML conversion failed!"
    exit 1
fi
fi

if [ "$START_FROM" -le 8 ]; then
echo ""
echo "[Step 8/10] Post-processing HTML files..."
if [ "$DOCKER" == true ]; then
    RUN_ARGS=(
      docker run --rm
      --user "$(id -u):$(id -g)"
      -v "$(pwd)":/app:rw
            md-converter src/docx_to_md/postprocessing.py "$HTML_DIRTY_DIR"
    )
    "${RUN_ARGS[@]}"
else
    python src/docx_to_md/postprocessing.py "$HTML_DIRTY_DIR"
fi
if [ $? -ne 0 ]; then
    echo "Error: postprocessing.py failed!"
    exit 1
fi
fi

if [ "$START_FROM" -le 9 ]; then
echo ""
echo "[Step 9/10] Converting HTML-dirty to Markdown..."
if [ "$DOCKER" == true ]; then
    RUN_ARGS=(
      docker run --rm
      --user "$(id -u):$(id -g)"
      -v "$(pwd)":/app:rw
      md-converter convert.py --frm html_dirty --to md --folder "$DOCX_BASENAME"
    )
    echo "Running in Docker: ${RUN_ARGS[*]}"
    "${RUN_ARGS[@]}"
    EXIT_CODE=$?
else
    python convert.py --frm html_dirty --to md --folder "$DOCX_BASENAME"
    EXIT_CODE=$?
fi

if [ $EXIT_CODE -ne 0 ]; then
    echo "Error: HTML to MD conversion failed (step 9)!"
    if [ -d "$HTML_DIRTY_DIR" ]; then
        echo "  - HTML files available:"
        ls -1 "$HTML_DIRTY_DIR" | sed 's/^/    /'
    else
        echo "  - HTML input dir does not exist"
    fi
    exit 1
fi
fi

# if [ "$START_FROM" -le 10 ]; then
# echo ""
# echo "[Step 10/10] Cleaning up Markdown files..."
# if [ "$DOCKER" == true ]; then
#     RUN_ARGS=(
#       docker run --rm
#       --user "$(id -u):$(id -g)"
#       -v "$(pwd)":/app:rw
#       md-converter cleanup_md.py --src "$MD_DIR"
#     )
#     "${RUN_ARGS[@]}"
# else
#     python cleanup_md.py --src "$MD_DIR"
# fi
# if [ $? -ne 0 ]; then
#     echo "Error: cleanup_md.py failed!"
#     exit 1
# fi
# fi

echo ""
echo "============================================================================"
echo "[Completed] Conversion completed successfully!"
echo "============================================================================"
echo ""
echo "Generated files are located in:"
echo "  - Markdown files: $MD_DIR"
echo "  - HTML (dirty):   $HTML_DIRTY_DIR"
echo ""
echo "You can now edit the Markdown files in: $MD_DIR"
echo "============================================================================"

exit 0