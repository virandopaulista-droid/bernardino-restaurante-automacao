#!/usr/bin/env bash
# Publishes 1+ Facebook Page Stories (immediate only — API has no scheduling
# and no caption/text field for Stories, unlike feed posts).
# Usage: post_story_fb.sh <image1> [image2 ...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${FB_PAGE_ACCESS_TOKEN:?Faltou FB_PAGE_ACCESS_TOKEN no .env}"
: "${FB_PAGE_ID:?Faltou FB_PAGE_ID no .env}"

FB_PAGE_ID="$FB_PAGE_ID" FB_PAGE_ACCESS_TOKEN="$FB_PAGE_ACCESS_TOKEN" python3 - "$@" <<'PYEOF'
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

def read_file_with_retry(path, attempts=6, delay_seconds=10):
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

image_paths = sys.argv[1:]
page_id = os.environ["FB_PAGE_ID"]
access_token = os.environ["FB_PAGE_ACCESS_TOKEN"]

def post_multipart(url, fields, files):
    boundary = uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode("utf-8")
    for name, filename, content in files:
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n").encode("utf-8") + content + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def post_form(url, fields):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode("utf-8"), method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

for image_path in image_paths:
    image_bytes = read_file_with_retry(image_path)
    try:
        photo_result = post_multipart(
            f"https://graph.facebook.com/v20.0/{page_id}/photos",
            {"access_token": access_token, "published": "false"},
            [("source", os.path.basename(image_path), image_bytes)],
        )
        story_result = post_form(
            f"https://graph.facebook.com/v20.0/{page_id}/photo_stories",
            {"access_token": access_token, "photo_id": photo_result["id"]},
        )
    except urllib.error.HTTPError as e:
        print(f"Erro da API do Facebook em {image_path}: {e.read().decode('utf-8')}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Story publicado: {image_path} -> {story_result}")
PYEOF
