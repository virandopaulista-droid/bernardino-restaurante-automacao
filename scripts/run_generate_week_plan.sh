#!/usr/bin/env bash
# Entry point for Windows Task Scheduler: generates next week's plan + gallery.
# Runs unattended (e.g. Sunday evening) so the plan is waiting for approval
# by the time Monday's posting windows start. Does NOT publish anywhere or
# post anything -- just selects/reserves media, writes captions, and builds
# the local HTML gallery for review.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

export OPENAI_API_KEY FB_PAGE_ACCESS_TOKEN FB_PAGE_ID IG_BUSINESS_ID
export MEDIA_DIR_IMAGES_2025 MEDIA_DIR_IMAGES_2026 MEDIA_DIR_VIDEOS MEDIA_DIR_STORIES_REELS

plan_path="$(python3 "$SCRIPT_DIR/generate_week_plan.py")"
echo "Plano gerado: $plan_path"

gallery_path="$(python3 "$SCRIPT_DIR/build_week_gallery.py" "$plan_path")"
echo "Galeria gerada: $gallery_path"

start "" "$gallery_path" 2>/dev/null || true
