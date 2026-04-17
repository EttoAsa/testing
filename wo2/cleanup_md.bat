@echo off
setlocal enabledelayedexpansion

set "ARCH=amd64"
set "SRC="
set "REBUILD=false"
set "APP_DIR=%CD%"

:parse_args
if "%~1"=="" goto args_done
if "%~1"=="--arch" (
  set "ARCH=%~2"
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
if "%~1"=="--rebuild" (
  set "REBUILD=true"
  shift
  goto parse_args
)
if "%~1"=="--help" (
  echo Usage: cleanup_md.bat [--arch <amd64|arm64>] [--rebuild] --src <file_or_directory>
  echo.
  echo Options:
  echo   --arch <amd64|arm64>  Specify the target architecture for the Docker image (default: amd64).
  echo   --src <file_or_directory>   Path to the source Markdown file or directory to process (required).
  echo   --rebuild              Rebuild the Docker image before running the cleanup.
  echo   --help                 Display this help message.
  exit /b 0
)
echo Unknown parameter passed: %~1
exit /b 1

:args_done
if "%ARCH%" NEQ "amd64" if "%ARCH%" NEQ "arm64" (
	echo Error: --arch must be either 'amd64' or 'arm64'
	exit /b 1
)
if "%SRC%"=="" (
  echo Error: --src argument is required.
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
rem check if SRC is a file or directory
set "SRC_TYPE="
set "SRC_DIR="
set "SRC_FILE="
if exist "%SRC%\*" (
  rem SRC is a directory
  set "SRC_TYPE=directory"
) else if exist "%SRC%" (
  rem SRC is a file
  set "SRC_TYPE=file"
  for %%I in ("%SRC%") do (
    set "SRC_DIR=%%~dpI"
    set "SRC_FILE=%%~nxI"
  )
) else (
  echo Error: The specified --src path does not exist.
  exit /b 1
)

if "%SRC_TYPE%"=="file" (
  rem Process the single file
  docker run --rm ^
    --user 1000:1000 ^
    -v "%APP_DIR%:/app:rw" ^
    -v "%SRC_DIR%:/data/sources:rw" ^
    md-converter cleanup_md.py --src "/data/sources/%SRC_FILE%"
) else if "%SRC_TYPE%"=="directory" (
  rem Process all .md files in the directory
  docker run --rm ^
    --user 1000:1000 ^
    -v "%APP_DIR%:/app:rw" ^
    -v "%SRC%:/data/sources:rw" ^
    md-converter cleanup_md.py --src "/data/sources"
)

endlocal