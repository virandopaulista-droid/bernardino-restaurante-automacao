#!/usr/bin/env bash
# Entry point for Windows Task Scheduler: sources .env then runs the poller.
# Usage: run_poller.sh [--live]   (default: dry-run, prints what it would do)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

export OPENAI_API_KEY FB_PAGE_ACCESS_TOKEN FB_PAGE_ID IG_BUSINESS_ID
export MEDIA_DIR_IMAGES_2025 MEDIA_DIR_IMAGES_2026 MEDIA_DIR_VIDEOS MEDIA_DIR_STORIES_REELS
export BRENDA_STORIES_DIR

python3 "$SCRIPT_DIR/poller.py" "$@"
