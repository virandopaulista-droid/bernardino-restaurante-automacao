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
    echo "== $category ($type): $path =="
    if [ "$type" = "image" ]; then
        bash "$SCRIPT_DIR/post_story_all.sh" "$path"
    else
        bash "$SCRIPT_DIR/post_story_video_fb.sh" "$path"
        fname="$(basename "$path")"
        video_url="$(python3 "$SCRIPT_DIR/resolve_drive_url.py" "$fname")"
        bash "$SCRIPT_DIR/post_story_video_instagram.sh" "$video_url"
    fi
done
