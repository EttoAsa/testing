@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM Script: docx_to_md.bat
REM 
REM Description: Automates the conversion process from DOCX to HTML-dirty to MD
REM              using Docker ONLY (md-converter image)
REM 
REM Usage: docx_to_md.bat --file <document_name> [--start-from <step>] [--arch <amd64|arm64>] [--rebuild]
REM        where <document_name> is the name without the .docx extension
REM        and <step> is the step number to start from (1-10)
REM 
REM Example: docx_to_md.bat --file ts104175
REM          docx_to_md.bat --file ts104175 --start-from 8
REM          (will skip to step 8, converting HTML-dirty to Markdown)
REM ============================================================================

set "DOC_INPUT="
set "START_FROM=1"
set "ARCH=amd64"
set "REBUILD=false"
set "SHOW_HELP=false"

if "%~1"=="" set "SHOW_HELP=true"

:parse_args
if "%~1"=="" goto args_done

set "PARAM=%~1"

if /I "!PARAM!"=="--file" (
    if "%~2"=="" (
        echo Error: --file requires a value.
        exit /b 1
    )
    set "DOC_INPUT=%~2"
    shift
    shift
    goto parse_args
) else if /I "!PARAM:~0,7!"=="--file=" (
    set "DOC_INPUT=!PARAM:~7!"
) else if /I "!PARAM!"=="--start-from" (
    if "%~2"=="" (
        echo Error: --start-from requires a value between 1 and 10.
        exit /b 1
    )
    set "START_FROM=%~2"
    echo !START_FROM!| findstr /r "^[1-9]$ ^10$" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo Error: --start-from must be a number between 1 and 10
        exit /b 1
    )
    echo Starting from step !START_FROM!
    shift
    shift
    goto parse_args
) else if /I "!PARAM:~0,13!"=="--start-from" (
    set "START_FROM=!PARAM:~13!"
    echo !START_FROM!| findstr /r "^[1-9]$ ^10$" >nul 2>&1
    if !ERRORLEVEL! neq 0 (
        echo Error: --start-from must be a number between 1 and 10
        exit /b 1
    )
    echo Starting from step !START_FROM!
) else if /I "!PARAM!"=="--arch" (
    if "%~2"=="" (
        echo Error: --arch requires a value: amd64 or arm64.
        exit /b 1
    )
    set "ARCH=%~2"
    if /I not "!ARCH!"=="amd64" if /I not "!ARCH!"=="arm64" (
        echo Error: --arch must be either amd64 or arm64
        exit /b 1
    )
    shift
    shift
    goto parse_args
) else if "!PARAM:~0,7!"=="--arch=" (
    set "ARCH=!PARAM:~7!"
    if /I not "!ARCH!"=="amd64" if /I not "!ARCH!"=="arm64" (
        echo Error: --arch must be either amd64 or arm64
        exit /b 1
    )
) else if /I "!PARAM!"=="--rebuild" (
    set "REBUILD=true"
) else if /I "!PARAM!"=="--help" (
    set "SHOW_HELP=true"
) else (
    echo Error: Invalid parameter: !PARAM!
    echo Use --help to see supported options.
    exit /b 1
)

shift
goto parse_args

:args_done

if /I "%SHOW_HELP%"=="true" (
    echo Usage: docx_to_md.bat --file ^<document_name_or_docx_path^> [--start-from ^<step^>] [--arch ^<amd64^|arm64^>] [--rebuild]
    echo.
    echo Options:
    echo   --file ^<value^>          Required. DOCX base name ^(e.g. ts104175^) or DOCX path
    echo   --start-from ^<step^>     Step number to start from ^(1-10, default: 1^)
    echo   --arch ^<amd64^|arm64^>   Architecture for Docker image ^(default: amd64^)
    echo   --rebuild                 Force rebuild of Docker image
    echo   --help                    Show this help message and exit
    echo.
    echo Examples:
    echo   docx_to_md.bat --file ts104175
    echo   docx_to_md.bat --file ts104175 --start-from 8
    echo   docx_to_md.bat --file .\GENERATED_FILES\ts104176\docx\document.docx
    exit /b 0
)

if "%DOC_INPUT%"=="" (
    echo Error: --file is required.
    echo Use --help to see supported options.
    exit /b 1
)

REM Check Docker availability
docker --version >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo Error: Docker is not installed or not available in PATH.
    exit /b 1
)

REM Build image if missing or if --rebuild is set
docker image inspect md-converter >nul 2>&1
if !ERRORLEVEL! neq 0 (
    echo Docker image md-converter not found. Building image...
    docker build --build-arg TARGETARCH=!ARCH! -t md-converter .
    if !ERRORLEVEL! neq 0 (
        echo Error: Docker image build failed!
        exit /b 1
    )
) else if /I "!REBUILD!"=="true" (
    echo Rebuilding Docker image md-converter for arch !ARCH!...
    docker build --build-arg TARGETARCH=!ARCH! -t md-converter .
    if !ERRORLEVEL! neq 0 (
        echo Error: Docker image rebuild failed!
        exit /b 1
    )
)

set "DOCX_FILE=%DOC_INPUT%"
if not exist "%DOCX_FILE%" (
    if /I not "%DOCX_FILE:~-5%"==".docx" (
        set "DOCX_FILE=%DOC_INPUT%.docx"
    )
)

for %%F in ("%DOCX_FILE%") do set "DOCX_FILE=%%~fF"

if not exist "%DOCX_FILE%" (
    echo Error: File "%DOCX_FILE%" not found.
    exit /b 1
)

set "WORKSPACE_ROOT=%CD%"
set "DOCX_FILE_UNIX=%DOCX_FILE%"
set "DOCX_FILE_UNIX=!DOCX_FILE_UNIX:%WORKSPACE_ROOT%=/app!"
set "DOCX_FILE_UNIX=!DOCX_FILE_UNIX:\=/!"

if /I not "!DOCX_FILE_UNIX:~0,5!"=="/app/" (
    echo Error: The DOCX file must be inside "%CD%" because Docker mounts only this directory.
    exit /b 1
)

for %%F in ("%DOCX_FILE%") do (
    set "DOC_FILENAME=%%~nxF"
    set "DOC_BASENAME=%%~nF"
    set "DOC_PARENT=%%~dpF"
)

set "FOLDER_NAME=!DOC_BASENAME!"

set "GENERATED_DIR=GENERATED_FILES\%FOLDER_NAME%"
set "TEMP_DIR=%GENERATED_DIR%\temp"
set "HTML_DIRTY_DIR=%GENERATED_DIR%\html_dirty"
set "MD_DIR=%GENERATED_DIR%\md"

set "GENERATED_DIR_UNIX=GENERATED_FILES/%FOLDER_NAME%"
set "TEMP_DIR_UNIX=%GENERATED_DIR_UNIX%/temp"
set "HTML_DIRTY_DIR_UNIX=%GENERATED_DIR_UNIX%/html_dirty"
set "MD_DIR_UNIX=%GENERATED_DIR_UNIX%/md"

echo ============================================================================
echo Starting DOCX to MD conversion for: %DOCX_FILE%
echo Docker mode: enabled ^(arch=!ARCH!^)
if !START_FROM! gtr 1 (
    echo ^(Skipping to step !START_FROM!^)
)
echo ============================================================================

if !START_FROM! leq 1 (
    echo.
    echo [Step 1/10] Cleaning up previous temporary files...
    if exist "%TEMP_DIR%" (
        rmdir /S /Q "%TEMP_DIR%"
        if !ERRORLEVEL! neq 0 (
            echo Warning: Failed to delete temp directory, continuing...
        )
    )
)

if !START_FROM! leq 2 (
    echo.
    echo [Step 2/10] Preprocessing DOCX file...
    docker run --rm -v "%CD%:/app:rw" md-converter src/docx_to_md/preprocessing.py "!DOCX_FILE_UNIX!"
    if !ERRORLEVEL! neq 0 (
        echo Error: preprocessing.py failed!
        exit /b 1
    )
)

if !START_FROM! leq 3 (
    echo.
    echo [Step 3/10] Copying CSS files...
    copy /Y customCSS.css "%GENERATED_DIR%\customCSS.css"
    if !ERRORLEVEL! neq 0 (
        echo Error: Failed to copy customCSS.css!
        exit /b 1
    )
)

if !START_FROM! leq 4 (
    echo.
    echo [Step 4/10] Extracting media from DOCX...
    docker run --rm -v "%CD%:/app:rw" --entrypoint pandoc md-converter --extract-media "/app/%TEMP_DIR_UNIX%" -f docx -t html "/app/%TEMP_DIR_UNIX%/temp.docx" -o "/app/%TEMP_DIR_UNIX%/%FOLDER_NAME%.html"
    if !ERRORLEVEL! neq 0 (
        echo Error: Pandoc media extraction failed!
        exit /b 1
    )
)

if !START_FROM! leq 5 (
    echo.
    echo [Step 5/10] Converting EMF images to PNG ^(LibreOffice, Docker^)...
    docker run --rm -v "%CD%:/app:rw" --entrypoint sh md-converter -c "if ls /app/%TEMP_DIR_UNIX%/media/*.emf 1> /dev/null 2>&1; then if command -v libreoffice > /dev/null 2>&1; then libreoffice --headless --convert-to png --outdir /app/%TEMP_DIR_UNIX%/media /app/%TEMP_DIR_UNIX%/media/*.emf; elif command -v soffice > /dev/null 2>&1; then soffice --headless --convert-to png --outdir /app/%TEMP_DIR_UNIX%/media /app/%TEMP_DIR_UNIX%/media/*.emf; else echo 'Warning: LibreOffice/soffice not found, skipping EMF conversion...'; fi; else echo 'No EMF files found, skipping conversion...'; fi"
    if !ERRORLEVEL! neq 0 (
        echo Warning: LibreOffice conversion had issues, continuing...
    )
)

if !START_FROM! leq 6 (
    echo.
    echo [Step 6/10] Trimming PNG images ^(ImageMagick, Docker^)...
    docker run --rm -v "%CD%:/app:rw" --entrypoint sh md-converter -c "if ls /app/%TEMP_DIR_UNIX%/media/*.png 1> /dev/null 2>&1; then if command -v mogrify > /dev/null 2>&1; then mogrify -trim /app/%TEMP_DIR_UNIX%/media/*.png; elif command -v magick > /dev/null 2>&1; then magick mogrify -trim /app/%TEMP_DIR_UNIX%/media/*.png; else echo 'Warning: ImageMagick not found, skipping trim...'; fi; else echo 'No PNG files found, skipping trim...'; fi"
    if !ERRORLEVEL! neq 0 (
        echo Warning: ImageMagick trim had issues, continuing...
    )
)

if !START_FROM! leq 7 (
    echo.
    echo [Step 7/10] Converting DOCX to HTML with Pandoc...
    REM Remove html_dirty directory if it exists to avoid Pandoc errors
    if exist "%HTML_DIRTY_DIR%" (
        echo Removing existing html_dirty directory...
        rmdir /S /Q "%HTML_DIRTY_DIR%"
    )
    docker run --rm -v "%CD%:/app:rw" --entrypoint pandoc md-converter --resource-path "/app/%TEMP_DIR_UNIX%" -f docx -t chunkedhtml -L src/docx_to_md/docx_to_html_styling.lua -L src/docx_to_md/docx_to_html_links.lua --css=/app/customCSS.css --css=/app/%FOLDER_NAME%.css -s "/app/%TEMP_DIR_UNIX%/temp.docx" -o "/app/%HTML_DIRTY_DIR_UNIX%" --toc --toc-depth 4 --template=official.html --split-level=1
    if !ERRORLEVEL! neq 0 (
        echo Error: Pandoc HTML conversion failed!
        exit /b 1
    )
)

if !START_FROM! leq 8 (
    echo.
    echo [Step 8/10] Post-processing HTML-dirty files...
    docker run --rm -v "%CD%:/app:rw" md-converter src/docx_to_md/postprocessing.py "/app/%HTML_DIRTY_DIR_UNIX%"
    if !ERRORLEVEL! neq 0 (
        echo Error: postprocessing.py failed!
        exit /b 1
    )
)

if !START_FROM! leq 9 (
    echo.
    echo [Step 9/10] Converting HTML-dirty to Markdown...
    docker run --rm -v "%CD%:/app:rw" md-converter convert.py --frm html_dirty --to md --folder "%FOLDER_NAME%"
    if !ERRORLEVEL! neq 0 (
        echo Error: HTML to MD conversion failed!
        exit /b 1
    )
)

if !START_FROM! leq 10 (
    echo.
    echo [Step 10/10] Cleaning up Markdown files...
    docker run --rm -v "%CD%:/app:rw" md-converter cleanup_md.py --src "/app/%MD_DIR_UNIX%"
    if !ERRORLEVEL! neq 0 (
        echo Error: cleanup_md.py failed!
        exit /b 1
    )
)

echo.
echo ============================================================================
echo [Completed] Conversion completed successfully!
echo ============================================================================
echo.
echo Generated files are located in:
echo   - Markdown files: %MD_DIR%
echo   - HTML (dirty):   %HTML_DIRTY_DIR%
echo.
echo You can now edit the Markdown files in: %MD_DIR%
echo ============================================================================

exit /b 0