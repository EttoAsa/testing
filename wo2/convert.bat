@echo off
setlocal enabledelayedexpansion

set "ARCH=amd64"
set "FRM="
set "TO="
set "FOLDER="
set "SRC="
set "FILE_ORDER="
set "DIFF=false"
set "GIT=false"
set "GIT_BRANCH="
set "REPO_SRC="
set "SRC_SUBFOLDER="
set "REBUILD=false"
set "NO_LAZY_TOC=false"
set "TIMER_ENABLED=false"
set "EXTRA_OUTPUTS="

:parse_args
if "%~1"=="" goto args_done
if "%~1"=="--frm" (
	set "FRM=%~2"
	shift
	shift
	goto parse_args
)
if "%~1"=="--to" (
	set "TO=%~2"
	shift
	shift
	goto parse_args
)
if "%~1"=="--folder" (
	set "FOLDER=%~2"
	shift
	shift
	goto parse_args
)
if "%~1"=="--src" (
	set "SRC=%~2"
	shift
	shift
	goto parse_args
)
if "%~1"=="--file-order" (
	set "FILE_ORDER=%~2"
	shift
	shift
	goto parse_args
)
if "%~1"=="--diff" (
	set "DIFF=true"
	shift
	goto parse_args
)
if "%~1"=="--diff-git" (
	set "GIT=true"
	set "NEXT=%~2"
	if "!NEXT!"=="" (
		set "GIT_BRANCH="
		shift
		goto parse_args
	)
	if "!NEXT:~0,2!"=="--" (
		set "GIT_BRANCH="
		shift
		goto parse_args
	)
	set "GIT_BRANCH=%~2"
	shift
	shift
	goto parse_args
)
if "%~1"=="--arch" (
	set "ARCH=%~2"
	shift
	shift
	goto parse_args
)
if "%~1"=="--rebuild" (
	set "REBUILD=true"
	shift
	goto parse_args
)
if "%~1"=="--time" (
	set "TIMER_ENABLED=true"
	shift
	goto parse_args
)
if "%~1"=="--no-lazy-toc" (
	set "NO_LAZY_TOC=true"
	shift
	goto parse_args
)
if "%~1"=="--extra-outputs" (
	set "EXTRA_OUTPUTS=%~2"
	shift
	shift
	goto parse_args
)
if "%~1"=="--help" (
	echo Usage: convert.bat --frm <format> --to <format> --folder <path> [options]
	echo.
	echo Required parameters:
	echo   --frm <format>        Source format (e.g., md)
	echo   --to <format>         Target format (e.g., html)
	echo   --folder <path>       Path to the folder containing files to convert
	echo.
	echo Optional parameters:
	echo   --src <path>          Path to source files (overrides --folder for source volume)
	echo   --file-order <file>   File specifying the order of conversion
	echo   --arch <arch>         Target architecture (amd64 or arm64^). Default is amd64.
	echo   --rebuild              Rebuild the Docker image before running
	echo   --time                 (for Debug) Enable timing of the conversion process
	echo   --extra-outputs ^<fmt^>  Extra outputs for html-^>docx: pdf, epub, or pdf,epub
	echo Optional parameters from md to html conversion (only applicable if --from md --to html):
	echo   --no-lazy-toc         Disable lazy loading of the Table of Contents (TOC)
	echo   --diff                 Enable diff conversion using folder-base
	echo   --diff-git <branch>    Enable git-based diff conversion. If specified, uses the input branch
	exit /b 0
)
echo Unknown parameter passed: %~1
exit /b 1
:args_done

if "%ARCH%" NEQ "amd64" if "%ARCH%" NEQ "arm64" (
	echo Error: --arch must be either 'amd64' or 'arm64'
	exit /b 1
)
rem Ensure the docker image exists; build if missing
docker image inspect md-converter >nul 2>&1
if errorlevel 1 (
	docker build --build-arg TARGETARCH=%ARCH% -t md-converter .
	if errorlevel 1 (
		echo Failed to build image md-converter.
		exit /b 1
	)
)
rem Rebuild the image if --rebuild is present
if "%REBUILD%"=="true" (
	docker build --build-arg TARGETARCH=%ARCH% -t md-converter .
	if errorlevel 1 (
		echo Failed to build image md-converter.
		exit /b 1
	)
)
if "%FRM%"=="" (
	echo Error: --frm is required.
	exit /b 1
)
if "%TO%"=="" (
	echo Error: --to is required.
	exit /b 1
)
if "%FOLDER%"=="" (
	echo Error: --folder is required.
	exit /b 1
)
if %GIT%==true if %DIFF%==true (
	echo Warning: --diff-git cannot be used together with --diff.
	echo "--diff-git overrides --diff. Continuing with --diff-git behavior."
	set "DIFF=false"
)
if defined EXTRA_OUTPUTS (
	if /I not "%EXTRA_OUTPUTS%"=="pdf" if /I not "%EXTRA_OUTPUTS%"=="epub" if /I not "%EXTRA_OUTPUTS%"=="pdf,epub" (
		echo Error: --extra-outputs must be one of: pdf, epub, pdf,epub
		exit /b 1
	)
	if /I not "%FRM%"=="html" (
		echo Error: --extra-outputs is valid only when --frm html --to docx
		exit /b 1
	)
	if /I not "%TO%"=="docx" (
		echo Error: --extra-outputs is valid only when --frm html --to docx
		exit /b 1
	)
)
if %GIT%==true if "%SRC%"=="" (
	echo Error: --diff-git requires --src to be specified.
	exit /b 1
)
set "SRC_VOL=%FOLDER%"
if defined SRC set "SRC_VOL=%SRC%"
if "%GIT%"=="true" (
	rem Convert relative path to absolute for proper .git detection
	pushd "%SRC_VOL%"
	if errorlevel 1 (
		echo Error: Cannot access source directory "%SRC_VOL%"
		exit /b 1
	)
	set "SRC_VOL_ABS=!CD!"
	popd
	
	if exist "!SRC_VOL_ABS!\.git" (
		rem SRC is a Git repository
		set "REPO_SRC=!SRC_VOL_ABS!"
	) else (
		pushd "!SRC_VOL_ABS!\.."
		if exist ".git" (
			rem SRC's parent is a Git repository
			rem Extract subfolder name
			for %%F in ("!SRC_VOL_ABS!") do set "SRC_SUBFOLDER=%%~nxF"
			rem Get parent directory absolute path
			set "REPO_SRC=!CD!"
		) else (
			rem WARNING: neither src nor its parent is a Git repository - Proceeding without diff
			set "DIFF=false"
			set "GIT=false"
			set "SRC_SUBFOLDER="
			set "REPO_SRC="
		)
		popd
	)
)
if defined REPO_SRC (
	set "SRC_VOL=%REPO_SRC%"
)
set "EXTRA_ARGS="
if defined SRC (
	if defined SRC_SUBFOLDER (
		set "EXTRA_ARGS=!EXTRA_ARGS! --src "/data/sources/!SRC_SUBFOLDER!""
	) else (
		set "EXTRA_ARGS=!EXTRA_ARGS! --src "/data/sources""
	)
)
if defined FILE_ORDER set "EXTRA_ARGS=!EXTRA_ARGS! --file-order "!FILE_ORDER!""
if %DIFF%==true set "EXTRA_ARGS=!EXTRA_ARGS! --diff"
if %GIT%==true (
	if defined GIT_BRANCH (
		set "EXTRA_ARGS=!EXTRA_ARGS! --diff-git "!GIT_BRANCH!""
	) else (
		set "EXTRA_ARGS=!EXTRA_ARGS! --diff-git"
	)
)
if %NO_LAZY_TOC%==true set "EXTRA_ARGS=!EXTRA_ARGS! --no-lazy-toc"
if %TIMER_ENABLED%==true set "EXTRA_ARGS=!EXTRA_ARGS! --time"
if defined EXTRA_OUTPUTS set "EXTRA_ARGS=!EXTRA_ARGS! --extra-outputs !EXTRA_OUTPUTS!"

set "APP_DIR=%CD%"
if defined EXTRA_ARGS (
	docker run --rm ^
		--user 1000:1000 ^
		-v "%APP_DIR%:/app:rw" ^
		-v "%SRC_VOL%:/data/sources:rw" ^
		md-converter convert.py ^
		--frm %FRM% ^
		--to %TO% ^
		--folder %FOLDER% ^
		!EXTRA_ARGS!
) else (
	docker run --rm ^
		--user 1000:1000 ^
		-v "%APP_DIR%:/app:rw" ^
		-v "%SRC_VOL%:/data/sources:rw" ^
		md-converter convert.py ^
		--frm %FRM% ^
		--to %TO% ^
		--folder %FOLDER%
)

endlocal