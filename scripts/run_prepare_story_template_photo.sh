#!/usr/bin/env bash
# Usage: run_prepare_story_template_photo.sh <prato_salgado|salada|doce>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${FB_PAGE_ACCESS_TOKEN:?Faltou FB_PAGE_ACCESS_TOKEN no .env}"
: "${FB_PAGE_ID:?Faltou FB_PAGE_ID no .env}"

FB_PAGE_ID="$FB_PAGE_ID" FB_PAGE_ACCESS_TOKEN="$FB_PAGE_ACCESS_TOKEN" \
MEDIA_DIR_IMAGES_2025="$MEDIA_DIR_IMAGES_2025" MEDIA_DIR_IMAGES_2026="$MEDIA_DIR_IMAGES_2026" \
MEDIA_DIR_STORIES_REELS="$MEDIA_DIR_STORIES_REELS" \
python3 "$SCRIPT_DIR/prepare_story_template_photo.py" "$@"
