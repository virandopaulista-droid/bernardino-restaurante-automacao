#!/usr/bin/env bash
# Usage: run_classify_media.sh [--limit=N]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${OPENAI_API_KEY:?Faltou OPENAI_API_KEY no .env}"
: "${MEDIA_DIR_IMAGES_2025:?Faltou MEDIA_DIR_IMAGES_2025 no .env}"

OPENAI_API_KEY="$OPENAI_API_KEY" \
MEDIA_DIR_IMAGES_2025="$MEDIA_DIR_IMAGES_2025" \
MEDIA_DIR_IMAGES_2026="$MEDIA_DIR_IMAGES_2026" \
MEDIA_DIR_VIDEOS="$MEDIA_DIR_VIDEOS" \
MEDIA_DIR_STORIES_REELS="$MEDIA_DIR_STORIES_REELS" \
python3 "$SCRIPT_DIR/classify_media.py" "$@"
