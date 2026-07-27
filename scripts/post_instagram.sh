#!/usr/bin/env bash
# Publishes an Instagram feed post (single or carousel) via the Content
# Publishing API. Immediate-publish only — Instagram has no scheduling
# parameter. Requires IG_BUSINESS_ID in .env (blocked until the Instagram
# Graph API product is added to the Meta app — see docs/guia-bernardino.md).
#
# Usage: post_instagram.sh <caption_file> <public_image_url1> [public_image_url2 ...]
#   Image URLs must be PUBLICLY reachable (Instagram fetches them itself) —
#   e.g. the PHOTO_URLS output from post_bernardino.sh's immediate-publish path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# shellcheck disable=SC1091
source "$PROJECT_DIR/.env"

: "${FB_PAGE_ACCESS_TOKEN:?Faltou FB_PAGE_ACCESS_TOKEN no .env}"
: "${IG_BUSINESS_ID:?Faltou IG_BUSINESS_ID no .env (Instagram ainda nao esta desbloqueado)}"

CAPTION_FILE="$1"
shift
IMAGE_URLS=("$@")

if [ "${#IMAGE_URLS[@]}" -eq 0 ]; then
  echo "Forneca ao menos 1 URL publica de imagem." >&2
  exit 1
fi

IG_BUSINESS_ID="$IG_BUSINESS_ID" FB_PAGE_ACCESS_TOKEN="$FB_PAGE_ACCESS_TOKEN" CAPTION_FILE="$CAPTION_FILE" python3 - "${IMAGE_URLS[@]}" <<'PYEOF'
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

image_urls = sys.argv[1:]
ig_id = os.environ["IG_BUSINESS_ID"]
access_token = os.environ["FB_PAGE_ACCESS_TOKEN"]

with open(os.environ["CAPTION_FILE"], "r", encoding="utf-8") as f:
    caption = f.read().strip()

def post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

try:
    if len(image_urls) == 1:
        container = post_form(
            f"https://graph.facebook.com/v20.0/{ig_id}/media",
            {"access_token": access_token, "image_url": image_urls[0], "caption": caption},
        )
    else:
        child_ids = []
        for url in image_urls:
            child = post_form(
                f"https://graph.facebook.com/v20.0/{ig_id}/media",
                {"access_token": access_token, "image_url": url, "is_carousel_item": "true"},
            )
            child_ids.append(child["id"])
        container = post_form(
            f"https://graph.facebook.com/v20.0/{ig_id}/media",
            {
                "access_token": access_token,
                "media_type": "CAROUSEL",
                "children": ",".join(child_ids),
                "caption": caption,
            },
        )

    publish_result = post_form(
        f"https://graph.facebook.com/v20.0/{ig_id}/media_publish",
        {"access_token": access_token, "creation_id": container["id"]},
    )
except urllib.error.HTTPError as e:
    print(f"Erro da API do Instagram: {e.read().decode('utf-8')}", file=sys.stderr)
    raise SystemExit(1)

print(json.dumps(publish_result), file=sys.stderr)
print(publish_result.get("id") or "")
PYEOF
