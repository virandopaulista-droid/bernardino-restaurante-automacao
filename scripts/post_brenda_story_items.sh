#!/usr/bin/env bash
# Posts a fixed list of Brenda-Stories assets (read from stdin, tab-separated
# category/type/path -- same format select_brenda_story.py prints) to
# Facebook + Instagram Stories. Does NOT select anything itself -- this is
# the reusable posting half, used both by post_brenda_story.sh (auto-select)
# and by the poller when posting pre-approved items from a week plan.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while IFS=$'\t' read -r category type path; do
    # strip a trailing \r -- python on Windows writes \r\n, and bash's `read`
    # only strips the final \n, leaving \r stuck to the last field (path)
    path="${path%$'\r'}"
    # A week plan generated on one machine (e.g. local Windows, G:\...) can be
    # posted from another (e.g. GitHub Actions' Linux rclone mount) -- if the
    # stored absolute path doesn't exist here, fall back to the filename
    # inside this environment's own BRENDA_STORIES_DIR.
    if [ ! -f "$path" ] && [ -n "${BRENDA_STORIES_DIR:-}" ]; then
        fallback="$BRENDA_STORIES_DIR/$(basename "$path")"
        if [ -f "$fallback" ]; then
            path="$fallback"
        fi
    fi
    echo "== $category ($type): $path =="
    if [ "$type" = "image" ]; then
        bash "$SCRIPT_DIR/post_story_all.sh" "$path" </dev/null
    else
        bash "$SCRIPT_DIR/post_story_video_fb.sh" "$path" </dev/null
        fname="$(basename "$path")"
        video_url="$(python3 "$SCRIPT_DIR/resolve_drive_url.py" "$fname" </dev/null)"
        bash "$SCRIPT_DIR/post_story_video_instagram.sh" "$video_url" </dev/null
    fi
done
