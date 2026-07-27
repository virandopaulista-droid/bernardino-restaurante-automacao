#!/usr/bin/env bash
# Publishes 1+ Instagram Stories. Image-only, immediate-publish, no caption
# field (Instagram Stories, like Facebook Stories, render no text via API).
# Usage: post_story_instagram.sh <public_image_url1> [public_image_url2 ...]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${FB_PAGE_ACCESS_TOKEN:?Faltou FB_PAGE_ACCESS_TOKEN no .env}"
: "${IG_BUSINESS_ID:?Faltou IG_BUSINESS_ID no .env}"

IG_BUSINESS_ID="$IG_BUSINESS_ID" FB_PAGE_ACCESS_TOKEN="$FB_PAGE_ACCESS_TOKEN" python3 - "$@" <<'PYEOF'
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

image_urls = sys.argv[1:]
ig_id = os.environ["IG_BUSINESS_ID"]
access_token = os.environ["FB_PAGE_ACCESS_TOKEN"]

def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

for url in image_urls:
    try:
        container = post_form(f"https://graph.facebook.com/v20.0/{ig_id}/media", {"access_token": access_token, "image_url": url, "media_type": "STORIES"})
        result = post_form(f"https://graph.facebook.com/v20.0/{ig_id}/media_publish", {"access_token": access_token, "creation_id": container["id"]})
    except urllib.error.HTTPError as e:
        print(f"Erro da API do Instagram para {url}: {e.read().decode('utf-8')}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Story publicado: {result}")
PYEOF
