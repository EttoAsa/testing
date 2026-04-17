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

FRM=""
TO=""
FOLDER=""
SRC=""
FILE_ORDER=""
DIFF=false
GIT=false
GIT_BRANCH=""
NO_LAZY_TOC=false
TIMER_ENABLED=false
EXTRA_OUTPUTS=""

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --frm) FRM="$2"; shift ;;
        --to) TO="$2"; shift ;;
        --folder) FOLDER="$2"; shift ;;
        --src) SRC="$2"; shift ;;
        --file-order) FILE_ORDER="$2"; shift ;;
        --arch) shift ;; # Already processed
        --diff) DIFF=true ;;
        --no-lazy-toc) NO_LAZY_TOC=true ;;
        --extra-outputs) EXTRA_OUTPUTS="$2"; shift ;;
        --diff-git)
            GIT=true
            if [[ -n "$2" && "$2" != --* ]]; then
                GIT_BRANCH="$2"
                shift
            else
                GIT_BRANCH=""
            fi
            ;;
        --time) TIMER_ENABLED=true ;;
        --rebuild) ;; # Already processed
        --help)
            echo "Usage: bash convert.sh --frm <format> --to <format> --folder <path> [options]"
            echo ""
            echo "Required parameters:"
            echo "  --frm <format>        Source format (e.g., md)"
            echo "  --to <format>         Target format (e.g., html)"
            echo "  --folder <path>       Path to the folder containing files to convert"
            echo ""
            echo "Optional parameters:"
            echo "  --src <path>          Path to source files (overrides --folder for source volume)"
            echo "  --file-order <file>   File specifying the order of conversion"
            echo "  --arch <arch>         Target architecture (amd64 or arm64). Default is amd64."
            echo "  --rebuild              Rebuild the Docker image before running"
            echo "  --time                 (for debug) Enable timing of the conversion process"
            echo "  --extra-outputs <fmt>  Extra outputs for html->docx: pdf, epub, or pdf,epub"
            echo "Optional parameters from md to html conversion (only applicable if --from md --to html):"
            echo "  --no-lazy-toc         Disable lazy loading of the Table of Contents (TOC)"
            echo "  --diff-git <branch>    Enable git-based diff conversion. If specified, uses the input branch"
            echo "  --diff                 Enable diff conversion using folder-base"
            exit 0
            ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done
# FRM, TO and FOLDER are required
if [[ -z "$FRM" || -z "$TO" || -z "$FOLDER" ]]; then
    echo "Error: --frm, --to, and --folder parameters are required."
    exit 1
fi
if [[ "$GIT" == true && -z "$SRC" ]]; then
    echo "Error: --src parameter is required when --diff-git is specified."
    exit 1
fi
if [[ "$GIT" == true && "$DIFF" == true ]]; then
    echo "Warning: --diff-git cannot be used together with --diff."
    echo "--diff-git overrides --diff. Continuing with --diff-git behavior."
    DIFF=false
fi
if [[ -n "$EXTRA_OUTPUTS" ]]; then
    if [[ "$EXTRA_OUTPUTS" != "pdf" && "$EXTRA_OUTPUTS" != "epub" && "$EXTRA_OUTPUTS" != "pdf,epub" ]]; then
        echo "Error: --extra-outputs must be one of: pdf, epub, pdf,epub"
        exit 1
    fi
    if [[ "$FRM" != "html" || "$TO" != "docx" ]]; then
        echo "Error: --extra-outputs is valid only when --frm html --to docx"
        exit 1
    fi
fi
SRC_VOL=""
if [[ -n "$SRC" ]]; then
    SRC_VOL="$SRC"
else
    SRC_VOL="$FOLDER"
fi

REPO_SRC=""
SRC_SUBFOLDER=""
# Validate Git repository path if --git is requested
if [[ "$GIT" == true ]]; then
    if [[ -d "$SRC_VOL/.git" ]]; then
        REPO_SRC="$SRC_VOL"
    elif [[ -n "$(dirname "$SRC_VOL")" && "$(dirname "$SRC_VOL")" != "." && -d "$(dirname "$SRC_VOL")/.git" ]]; then
        REPO_SRC="$(dirname "$SRC_VOL")"
        SRC_SUBFOLDER="$(basename "$SRC_VOL")"
    else
        echo "WARNING: neither the src nor its parent is a Git repository (.git missing). Proceeding without diff."
        DIFF=false
        GIT=false
        SRC_SUBFOLDER=""
        REPO_SRC=""
    fi
fi
if [[ -n "$REPO_SRC" ]]; then
    SRC_VOL="$REPO_SRC"
fi


# Build docker run arguments array
RUN_ARGS=(
  docker run --rm
  --user "$(id -u):$(id -g)"
  -v "$(pwd)":/app:rw
  -v "$SRC_VOL":/data/sources:rw
  md-converter convert.py
  --frm "$FRM"
  --to "$TO"
  --folder "$FOLDER"
)

# Add source mount argument
if [[ -n "$SRC_SUBFOLDER" ]]; then
    RUN_ARGS+=(--src "/data/sources/$SRC_SUBFOLDER")
elif [[ -n "$SRC" ]]; then
    RUN_ARGS+=(--src /data/sources)
fi
[[ -n "$FILE_ORDER" ]] && RUN_ARGS+=("--file-order" "$FILE_ORDER")
[[ "$DIFF" == true ]] && RUN_ARGS+=("--diff")
[[ "$GIT" == true ]] && RUN_ARGS+=("--diff-git" "$GIT_BRANCH")
[[ "$NO_LAZY_TOC" == true ]] && RUN_ARGS+=("--no-lazy-toc")
[[ "$TIMER_ENABLED" == true ]] && RUN_ARGS+=("--time")
[[ -n "$EXTRA_OUTPUTS" ]] && RUN_ARGS+=("--extra-outputs" "$EXTRA_OUTPUTS")

"${RUN_ARGS[@]}"

