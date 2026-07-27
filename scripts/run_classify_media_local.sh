#!/usr/bin/env bash
# Free alternative to run_classify_media.sh: uses local CLIP instead of the
# OpenAI vision API, no per-image cost.
# Usage: run_classify_media_local.sh [--limit=N]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${MEDIA_DIR_IMAGES_2025:?Faltou MEDIA_DIR_IMAGES_2025 no .env}"

MEDIA_DIR_IMAGES_2025="$MEDIA_DIR_IMAGES_2025" \
MEDIA_DIR_IMAGES_2026="$MEDIA_DIR_IMAGES_2026" \
MEDIA_DIR_VIDEOS="$MEDIA_DIR_VIDEOS" \
MEDIA_DIR_STORIES_REELS="$MEDIA_DIR_STORIES_REELS" \
python3 "$SCRIPT_DIR/classify_media_local.py" "$@"
