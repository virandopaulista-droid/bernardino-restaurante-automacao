#!/usr/bin/env python3
"""Permanently excludes a photo from ever being selected again (different from
'used', which just means already posted) — for cases like a photo showing a
staff member who no longer works there, a since-changed menu item, etc.

Usage: exclude_media.py <filename_or_path_substring> <reason>
"""
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0])
from lib_media import load_manifest, save_manifest

needle = sys.argv[1]
reason = sys.argv[2]

manifest = load_manifest()
matches = [e for e in manifest["images"] if needle in e["source_path"]]

if not matches:
    print(f"Nenhuma entrada encontrada contendo '{needle}'.", file=sys.stderr)
    raise SystemExit(1)

for entry in matches:
    entry["excluded"] = True
    entry["exclude_reason"] = reason

save_manifest(manifest)
for entry in matches:
    print(f"Excluida: {entry['source_path']}")
