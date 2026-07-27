#!/usr/bin/env bash
# Publishes an Instagram video Story from a public video URL. Facebook's own
# video CDN links don't work for this (ephemeral/DASH, confirmed by testing
# with Reels) -- use a Google Drive direct-download link instead, same fix
# used for Reels. No caption field (Instagram Stories don't support one).
# Usage: post_story_video_instagram.sh <public_video_url>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${FB_PAGE_ACCESS_TOKEN:?Faltou FB_PAGE_ACCESS_TOKEN no .env}"
: "${IG_BUSINESS_ID:?Faltou IG_BUSINESS_ID no .env}"

VIDEO_URL="$1"

IG_BUSINESS_ID="$IG_BUSINESS_ID" FB_PAGE_ACCESS_TOKEN="$FB_PAGE_ACCESS_TOKEN" VIDEO_URL="$VIDEO_URL" python3 <<'PYEOF'
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ig_id = os.environ["IG_BUSINESS_ID"]
access_token = os.environ["FB_PAGE_ACCESS_TOKEN"]
video_url = os.environ["VIDEO_URL"]


def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_json(url, params):
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", method="GET")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


try:
    container = post_form(
        f"https://graph.facebook.com/v20.0/{ig_id}/media",
        {"access_token": access_token, "media_type": "STORIES", "video_url": video_url},
    )
    container_id = container["id"]

    for _ in range(20):
        time.sleep(10)
        status = get_json(f"https://graph.facebook.com/v20.0/{container_id}", {"fields": "status_code,status", "access_token": access_token})
        print(f"status: {status}", file=sys.stderr)
        if status["status_code"] == "FINISHED":
            break
        if status["status_code"] == "ERROR":
            print(f"ERRO: processamento do story falhou: {status}", file=sys.stderr)
            raise SystemExit(1)
    else:
        print("ERRO: timeout esperando o video processar.", file=sys.stderr)
        raise SystemExit(1)

    publish_result = post_form(
        f"https://graph.facebook.com/v20.0/{ig_id}/media_publish",
        {"access_token": access_token, "creation_id": container_id},
    )
except urllib.error.HTTPError as e:
    print(f"Erro da API do Instagram: {e.read().decode('utf-8')}", file=sys.stderr)
    raise SystemExit(1)

print(f"IG video story publicado: {publish_result}")
PYEOF
