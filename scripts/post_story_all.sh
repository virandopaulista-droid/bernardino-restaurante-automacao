#!/usr/bin/env bash
# Publishes 1+ Stories to BOTH Facebook and Instagram from local image paths.
# Uploads each photo once (unpublished) to get a public CDN URL, reused for
# both the FB photo_stories call and the IG media (STORIES) call.
# Usage: post_story_all.sh <image1> [image2 ...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${FB_PAGE_ACCESS_TOKEN:?Faltou FB_PAGE_ACCESS_TOKEN no .env}"
: "${FB_PAGE_ID:?Faltou FB_PAGE_ID no .env}"
: "${IG_BUSINESS_ID:?Faltou IG_BUSINESS_ID no .env}"

FB_PAGE_ID="$FB_PAGE_ID" FB_PAGE_ACCESS_TOKEN="$FB_PAGE_ACCESS_TOKEN" IG_BUSINESS_ID="$IG_BUSINESS_ID" python3 - "$@" <<'PYEOF'
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

image_paths = sys.argv[1:]
page_id = os.environ["FB_PAGE_ID"]
ig_id = os.environ["IG_BUSINESS_ID"]
token = os.environ["FB_PAGE_ACCESS_TOKEN"]


def post_multipart(url, fields, files):
    import uuid
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


def get_json(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())


def post_form_retry(url, fields, retries=5, delay=4):
    import time
    for attempt in range(1, retries + 1):
        try:
            return post_form(url, fields)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            if attempt == retries or "2207027" not in body:
                raise
            print(f"  (midia ainda nao pronta no IG, tentativa {attempt}/{retries}, aguardando {delay}s...)", file=sys.stderr)
            time.sleep(delay)


for image_path in image_paths:
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    try:
        photo_result = post_multipart(
            f"https://graph.facebook.com/v20.0/{page_id}/photos",
            {"access_token": token, "published": "false"},
            [("source", os.path.basename(image_path), image_bytes)],
        )
        info = get_json(f"https://graph.facebook.com/v20.0/{photo_result['id']}?fields=images&access_token={token}")
        public_url = info["images"][0]["source"]

        fb_story = post_form(
            f"https://graph.facebook.com/v20.0/{page_id}/photo_stories",
            {"access_token": token, "photo_id": photo_result["id"]},
        )
        print(f"FB story publicado: {image_path} -> {fb_story}")

        container = post_form_retry(
            f"https://graph.facebook.com/v20.0/{ig_id}/media",
            {"access_token": token, "image_url": public_url, "media_type": "STORIES"},
        )
        ig_story = post_form_retry(
            f"https://graph.facebook.com/v20.0/{ig_id}/media_publish",
            {"access_token": token, "creation_id": container["id"]},
        )
        print(f"IG story publicado: {image_path} -> {ig_story}")
    except urllib.error.HTTPError as e:
        print(f"Erro da API em {image_path}: {e.read().decode('utf-8')}", file=sys.stderr)
        raise SystemExit(1)
PYEOF
