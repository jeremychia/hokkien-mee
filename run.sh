#!/usr/bin/env bash
# run.sh — Run the hokkien-mee extraction and mapping pipeline.
#
# Usage:
#   ./run.sh              Run all steps (extract, download images, map)
#   ./run.sh extract      Extract posts only
#   ./run.sh images       Download images only
#   ./run.sh map          Generate map only
#   ./run.sh all          Run all steps (same as no argument)
#
# Options are passed through to the underlying scripts.
# For example:
#   ./run.sh extract --pages 20 --debug

set -euo pipefail
cd "$(dirname "$0")"

# ---------- helpers ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { echo -e "${BOLD}▸ $1${NC}"; }
ok()    { echo -e "${GREEN}✓ $1${NC}"; }
err()   { echo -e "${RED}✗ $1${NC}" >&2; }

# ---------- pre-flight checks ----------
preflight() {
    if ! command -v uv &>/dev/null; then
        err "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi

    if [ ! -f "facebook_cookies.txt" ]; then
        err "facebook_cookies.txt not found. See README.md for setup instructions."
        exit 1
    fi

    if [ ! -f "secrets/secrets.py" ]; then
        err "secrets/secrets.py not found. See README.md for OneMap setup."
        exit 1
    fi
}

# ---------- steps ----------
step_extract() {
    info "Extracting posts from Facebook group..."
    uv run python extractor/extract_group.py "$@"
    ok "Extraction complete → output/group_posts.json"
}

step_images() {
    info "Downloading images..."
    uv run python extractor/download_images.py
    ok "Images downloaded → output/images/"
}

step_map() {
    info "Geocoding locations and building map..."
    uv run python extractor/map_posts.py
    ok "Map generated → docs/index.html"
}

# ---------- main ----------
main() {
    local cmd="${1:-all}"
    
    # If first arg starts with -, treat it as "all" with options
    if [[ "$cmd" == -* ]]; then
        cmd="all"
    else
        shift 2>/dev/null || true  # Remove the command from args
    fi

    case "$cmd" in
        extract)
            preflight
            step_extract "$@"
            ;;
        images)
            preflight
            step_images
            ;;
        map)
            preflight
            step_map
            ;;
        all)
            preflight
            step_extract "$@"
            echo
            step_images
            echo
            step_map
            ;;
        -h|--help|help)
            sed -n '2,14p' "$0" | sed 's/^#[[:space:]]*//'
            ;;
        *)
            err "Unknown command: $cmd"
            echo "Usage: ./run.sh [extract|images|map|all|help]"
            exit 1
            ;;
    esac
}

main "$@"
