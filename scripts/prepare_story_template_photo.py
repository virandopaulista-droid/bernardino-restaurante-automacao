#!/usr/bin/env python3
"""Picks one unused photo of the given category, marks it used, uploads it
unpublished to the Facebook Page to get a public CDN URL (needed for Canva's
upload-asset-from-url, which requires an already-public source).

This is the scriptable half of the Canva-templated-story pipeline — see
content/canva_story_templates.json for the other half (which Canva design/
element to swap the photo into). That part still requires an agent turn with
Canva MCP access (upload-asset-from-url, edit-design, export-design are not
callable from a headless script — no standalone Canva API credentials exist
in this project, only the MCP connection available inside an agent session).

Usage: prepare_story_template_photo.py <prato_salgado|salada|doce>
Prints: <local_photo_path>\t<public_cdn_url>
"""
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from select_media import mark_used, pick_image, pick_image_any
from lib_media import load_manifest, save_manifest

CATEGORY = sys.argv[1]
if CATEGORY not in ("prato_salgado", "salada", "doce"):
    print("Uso: prepare_story_template_photo.py <prato_salgado|salada|doce>", file=sys.stderr)
    raise SystemExit(1)

manifest = load_manifest()
entry = pick_image(manifest, CATEGORY) or pick_image_any(manifest)
if entry is None:
    print(f"ERRO: nenhuma foto disponivel pra categoria {CATEGORY}.", file=sys.stderr)
    raise SystemExit(1)
mark_used(entry)
save_manifest(manifest)

photo_path = entry["converted_path"]

page_id = os.environ["FB_PAGE_ID"]
token = os.environ["FB_PAGE_ACCESS_TOKEN"]

with open(photo_path, "rb") as f:
    image_bytes = f.read()

boundary = uuid.uuid4().hex
body = b""
body += f'--{boundary}\r\nContent-Disposition: form-data; name="access_token"\r\n\r\n{token}\r\n'.encode()
body += f'--{boundary}\r\nContent-Disposition: form-data; name="published"\r\n\r\nfalse\r\n'.encode()
mime = mimetypes.guess_type(photo_path)[0] or "image/jpeg"
body += (
    f'--{boundary}\r\nContent-Disposition: form-data; name="source"; filename="p.jpg"\r\nContent-Type: {mime}\r\n\r\n'
).encode() + image_bytes + b"\r\n"
body += f"--{boundary}--\r\n".encode()

req = urllib.request.Request(
    f"https://graph.facebook.com/v20.0/{page_id}/photos",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)
try:
    with urllib.request.urlopen(req) as resp:
        upload_result = json.loads(resp.read())
    info_req = urllib.request.Request(
        f"https://graph.facebook.com/v20.0/{upload_result['id']}?fields=images&access_token={token}"
    )
    with urllib.request.urlopen(info_req) as resp:
        info = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"Erro da API do Facebook: {e.read().decode('utf-8')}", file=sys.stderr)
    raise SystemExit(1)

url = info["images"][0]["source"]
print(f"{photo_path}\t{url}")
