#!/bin/bash

# Script to run docker conversion with parameters
ARCH="amd64"
REBUILD=false

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
done

# Validate arch parameter
if [[ "$ARCH" != "amd64" && "$ARCH" != "arm64" ]]; then
    echo "Error: --arch must be either 'amd64' or 'arm64'"
    exit 1
fi

# Check if image exists and rebuild if needed
if ! docker image inspect md-converter &>/dev/null || [[ "$REBUILD" == true ]]; then
  docker build --build-arg TARGETARCH="$ARCH" -t md-converter .
fi

SRC=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --src) SRC="$2"; shift ;;
        --arch) shift ;; # Already processed
        --rebuild) shift ;; # Already processed
        --help)
            echo "Usage: $0 [--arch <amd64|arm64>] [--rebuild] --src <file_or_directory>"
            echo ""
            echo "Options:"
            echo "  --arch <amd64|arm64>   Specify the architecture for the Docker image (default: amd64)"
            echo "  --rebuild              Force rebuild of the Docker image"
            echo "  --src <file_or_directory>  Path to the source Markdown file or directory to process (required)"
            echo "  --help                 Show this help message and exit"
            exit 0
            ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

if [[ -z "$SRC" ]]; then
    echo "Error: --src parameter is required"
    exit 1
fi

# Check if src is a file or a directory
SRC_DIR=""
if [[ -f "$SRC" ]]; then
    SRC="$(realpath "$SRC")"
    SRC_DIR=false
elif [[ -d "$SRC" ]]; then
    SRC="$(realpath "$SRC")"
    SRC_DIR=true
else
    echo "Error: --src must be a valid file or directory"
    exit 1
fi
if [[ ! -r "$SRC" ]]; then
    echo "Error: The file or directory $SRC is not readable."
    exit 1
fi
RUN_ARGS=""
if [[ "$SRC_DIR" == false ]]; then
    echo "Processing file: $SRC"
    RUN_ARGS=(
      docker run --rm
      --user "$(id -u):$(id -g)"
      -v "$(pwd)":/app:rw
      -v "$(dirname "$SRC")":/data/sources:rw
      md-converter cleanup_md.py
      --src /data/sources/$(basename "$SRC")
    )
else
    echo "Processing directory: $SRC"
    RUN_ARGS=(
      docker run --rm
      --user "$(id -u):$(id -g)"
      -v "$(pwd)":/app:rw
      -v "$SRC":/data/sources:rw
      md-converter cleanup_md.py
      --src /data/sources
    )
fi

# Run the docker command
"${RUN_ARGS[@]}"