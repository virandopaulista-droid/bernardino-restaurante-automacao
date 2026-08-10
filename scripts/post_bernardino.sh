#!/usr/bin/env bash
# Publishes a Bernardino Restaurante FEED post (static or carousel) to Facebook.
# When publishing immediately (schedule_at = "now"), also prints the resulting
# public CDN photo URL(s) on stdout (prefixed PHOTO_URLS:) — these are what
# post_instagram.sh needs as image_url, since Instagram's Content Publishing
# API requires a publicly-hosted URL and won't take raw bytes like Facebook's
# /photos endpoint does. Scheduled posts print no URLs (photo isn't public yet).
#
# Usage: post_bernardino.sh <caption_file> <schedule_at_unix|now> <image1> [image2 ...]
#   caption_file      path to a text file with the ready-to-publish caption
#   schedule_at_unix  unix timestamp to schedule the post, or the literal "now"
#   image1..N         1 image = static post, 2+ = carousel (already upload-ready JPEGs)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${FB_PAGE_ACCESS_TOKEN:?Faltou FB_PAGE_ACCESS_TOKEN no .env}"
: "${FB_PAGE_ID:?Faltou FB_PAGE_ID no .env}"

CAPTION_FILE="$1"
SCHEDULE_ARG="$2"
shift 2
IMAGE_PATHS=("$@")

if [ "${#IMAGE_PATHS[@]}" -eq 0 ]; then
  echo "Forneca ao menos 1 imagem." >&2
  exit 1
fi

SCHEDULE_AT=""
if [ "$SCHEDULE_ARG" != "now" ]; then
  SCHEDULE_AT="$SCHEDULE_ARG"
fi

CAPTION_TEXT="$(cat "$CAPTION_FILE")"

RESULT="$(FB_PAGE_ID="$FB_PAGE_ID" FB_PAGE_ACCESS_TOKEN="$FB_PAGE_ACCESS_TOKEN" SCHEDULE_AT="$SCHEDULE_AT" CAPTION_FILE="$CAPTION_FILE" python3 - "${IMAGE_PATHS[@]}" <<'PYEOF'
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
schedule_at = os.environ.get("SCHEDULE_AT", "").strip()

with open(os.environ["CAPTION_FILE"], "r", encoding="utf-8") as f:
    caption = f.read().strip()

boundary = uuid.uuid4().hex

def text_field(name, value):
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{value}\r\n"
    ).encode("utf-8")

def file_field(name, filename, content):
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    return header + content + b"\r\n"

def post_multipart(url, fields, files):
    body = b""
    for name, value in fields.items():
        body += text_field(name, value)
    for name, filename, content in files:
        body += file_field(name, filename, content)
    body += f"--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def get_json(url, params):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", method="GET")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def public_photo_url(photo_id):
    data = get_json(f"https://graph.facebook.com/v20.0/{photo_id}", {"fields": "images", "access_token": access_token})
    images = data.get("images") or []
    return images[0]["source"] if images else None

uploaded_photo_ids = []

try:
    if len(image_paths) == 1:
        image_path = image_paths[0]
        image_bytes = read_file_with_retry(image_path)
        if schedule_at:
            photo_result = post_multipart(
                f"https://graph.facebook.com/v20.0/{page_id}/photos",
                {"access_token": access_token, "published": "false"},
                [("source", os.path.basename(image_path), image_bytes)],
            )
            photo_id = photo_result["id"]
            result = post_form(
                f"https://graph.facebook.com/v20.0/{page_id}/feed",
                {
                    "access_token": access_token,
                    "message": caption,
                    "attached_media[0]": json.dumps({"media_fbid": photo_id}),
                    "published": "false",
                    "scheduled_publish_time": schedule_at,
                },
            )
        else:
            result = post_multipart(
                f"https://graph.facebook.com/v20.0/{page_id}/photos",
                {"access_token": access_token, "message": caption},
                [("source", os.path.basename(image_path), image_bytes)],
            )
            uploaded_photo_ids.append(result["id"])
    else:
        # Carousel: upload each photo unpublished first, then reference all of them in one /feed post.
        media_fields = {"access_token": access_token, "message": caption}
        for i, image_path in enumerate(image_paths):
            image_bytes = read_file_with_retry(image_path)
            photo_result = post_multipart(
                f"https://graph.facebook.com/v20.0/{page_id}/photos",
                {"access_token": access_token, "published": "false"},
                [("source", os.path.basename(image_path), image_bytes)],
            )
            media_fields[f"attached_media[{i}]"] = json.dumps({"media_fbid": photo_result["id"]})
            uploaded_photo_ids.append(photo_result["id"])

        if schedule_at:
            media_fields["published"] = "false"
            media_fields["scheduled_publish_time"] = schedule_at
        result = post_form(f"https://graph.facebook.com/v20.0/{page_id}/feed", media_fields)

    photo_urls = [] if schedule_at else [u for u in (public_photo_url(pid) for pid in uploaded_photo_ids) if u]
except urllib.error.HTTPError as e:
    print(f"Erro da API do Facebook: {e.read().decode('utf-8')}", file=sys.stderr)
    raise SystemExit(1)

print(json.dumps(result), file=sys.stderr)
print(result.get("post_id") or result.get("id") or "")
print(json.dumps(photo_urls))
PYEOF
)"

POST_ID="$(printf '%s' "$RESULT" | sed -n '1p')"
PHOTO_URLS_JSON="$(printf '%s' "$RESULT" | sed -n '2p')"

if [ -z "$POST_ID" ]; then
  echo "ERRO: Facebook nao retornou post_id/id. Veja a resposta acima." >&2
  exit 1
fi

if [ -n "$SCHEDULE_AT" ]; then
  echo "Agendado! Post ID: $POST_ID (vai ao ar em $(date -d @${SCHEDULE_AT} '+%Y-%m-%d %H:%M' 2>/dev/null || echo "unix:$SCHEDULE_AT"))"
else
  echo "Publicado! Post ID: $POST_ID"
fi
echo "PHOTO_URLS:$PHOTO_URLS_JSON"

POST_ID="$POST_ID" SCHEDULE_AT="$SCHEDULE_AT" python3 - "$PROJECT_DIR/content/posts-history.json" "${IMAGE_PATHS[@]}" <<'PYEOF'
import datetime
import json
import os
import sys

history_path = sys.argv[1]
image_paths = sys.argv[2:]
post_id = os.environ["POST_ID"]
schedule_at = os.environ.get("SCHEDULE_AT", "").strip()

try:
    with open(history_path, "r", encoding="utf-8") as f:
        data = json.load(f)
except FileNotFoundError:
    data = {"posts": []}

entry = {
    "date": datetime.datetime.now().isoformat(timespec="seconds"),
    "image_paths": image_paths,
    "fb_post_id": post_id,
}
if schedule_at:
    entry["scheduled_publish_time"] = int(schedule_at)

data["posts"].append(entry)

with open(history_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PYEOF

echo "Historico atualizado."
