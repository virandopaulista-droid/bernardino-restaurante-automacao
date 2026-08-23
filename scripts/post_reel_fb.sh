#!/usr/bin/env bash
# Publishes a Facebook Reel via the resumable Video Reels upload API
# (start -> upload bytes -> finish). Immediate-publish only, no scheduling.
# Usage: post_reel_fb.sh <video_path> <caption_file>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${FB_PAGE_ACCESS_TOKEN:?Faltou FB_PAGE_ACCESS_TOKEN no .env}"
: "${FB_PAGE_ID:?Faltou FB_PAGE_ID no .env}"

VIDEO_PATH="$1"
CAPTION_FILE="$2"

FB_PAGE_ID="$FB_PAGE_ID" FB_PAGE_ACCESS_TOKEN="$FB_PAGE_ACCESS_TOKEN" CAPTION_FILE="$CAPTION_FILE" python3 - "$VIDEO_PATH" <<'PYEOF'
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

def read_file_with_retry(path, attempts=18, delay_seconds=20):
    # The Drive mount (rclone, minimal VFS cache) sometimes 404s a file that
    # genuinely exists on Google Drive (confirmed via the Drive API) -- a
    # retry-with-backoff clears this most of the time instead of silently
    # failing a real scheduled post.
    for attempt in range(1, attempts + 1):
        try:
            os.listdir(os.path.dirname(path))
        except OSError:
            pass
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            if attempt == attempts:
                raise
            print(f"AVISO: {path} nao encontrado (tentativa {attempt}/{attempts}), tentando de novo em {delay_seconds}s...", file=sys.stderr)
            time.sleep(delay_seconds)

video_path = sys.argv[1]
page_id = os.environ["FB_PAGE_ID"]
access_token = os.environ["FB_PAGE_ACCESS_TOKEN"]

with open(os.environ["CAPTION_FILE"], "r", encoding="utf-8") as f:
    caption = f.read().strip()

def post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode("utf-8"), method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

try:
    start = post_form(
        f"https://graph.facebook.com/v20.0/{page_id}/video_reels",
        {"access_token": access_token, "upload_phase": "start"},
    )
    video_id = start["video_id"]
    upload_url = start["upload_url"]

    video_bytes = read_file_with_retry(video_path)

    upload_req = urllib.request.Request(
        upload_url,
        data=video_bytes,
        headers={
            "Authorization": f"OAuth {access_token}",
            "offset": "0",
            "file_size": str(len(video_bytes)),
        },
        method="POST",
    )
    with urllib.request.urlopen(upload_req) as resp:
        upload_result = json.loads(resp.read())

    finish = post_form(
        f"https://graph.facebook.com/v20.0/{page_id}/video_reels",
        {
            "access_token": access_token,
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": caption,
        },
    )
except urllib.error.HTTPError as e:
    print(f"Erro da API do Facebook: {e.read().decode('utf-8')}", file=sys.stderr)
    raise SystemExit(1)

print(json.dumps({"upload": upload_result, "finish": finish}), file=sys.stderr)
print(video_id)
PYEOF
