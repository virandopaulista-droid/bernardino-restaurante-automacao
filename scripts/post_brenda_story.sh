#!/usr/bin/env bash
# Posts today's 3 Brenda-Stories assets (prato do dia / salada / doce) to
# Facebook + Instagram Stories. Images: fully automatic (FB+IG) via
# post_story_all.sh. Videos: FB posts from the local file; Instagram needs a
# public video URL (Facebook's own CDN video links don't work for IG,
# confirmed with Reels) -- resolved automatically via resolve_drive_url.py
# (scrapes the shared folder's public embed view for the file's Drive ID,
# no Drive API credentials needed).
# Usage: post_brenda_story.sh [segunda|terca|quarta|quinta|sexta]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 "$SCRIPT_DIR/select_brenda_story.py" "$@" | bash "$SCRIPT_DIR/post_brenda_story_items.sh"
