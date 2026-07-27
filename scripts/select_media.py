#!/usr/bin/env python3
"""Picks unused media for the next post and marks it used in the manifest.

Usage:
  select_media.py story   -> prints 3 paths (salgado, salada, doce), one per line
  select_media.py feed    -> prints 5 paths for a carousel (mix: 2x prato_salgado, 1x salada, 1x doce, 1x ambiente),
                             falling back to any available category if one runs short
  select_media.py reel    -> prints 1 video path (from Videos Tratados / Stories Reels dump)

Marks whatever it picks as used=true immediately (this script's whole job is
"pick and reserve" — call it once per real post, not for browsing).
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_media import PROJECT_DIR, get_audio_mean_volume_db, get_video_duration_seconds, iter_video_files, load_manifest, save_manifest

VIDEO_MANIFEST_PATH = PROJECT_DIR / "content" / "video_manifest.json"
MIN_REEL_DURATION_SECONDS = 6  # user rule 2026-07-27: a 5s clip read as a static image on Instagram
MIN_REEL_AUDIO_DB = -40  # user rule 2026-07-27: a clip with a present-but-silent (-91dB) audio track posted with no sound


def load_video_manifest():
    import json
    if VIDEO_MANIFEST_PATH.exists():
        with open(VIDEO_MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"videos": []}
    known = {v["path"] for v in data["videos"]}
    for path in iter_video_files():
        p = str(path)
        if p not in known:
            data["videos"].append({
                "path": p, "used": False, "used_at": None,
                "duration_seconds": None, "too_short": False,
                "audio_mean_db": None, "silent": False,
            })
            known.add(p)
    return data


def save_video_manifest(data):
    import json
    with open(VIDEO_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pick_image(manifest, category, exclude_review=True):
    for entry in manifest["images"]:
        if entry["used"] or entry.get("excluded"):
            continue
        if entry["category"] != category:
            continue
        if exclude_review and entry.get("needs_review"):
            continue
        return entry
    if exclude_review:
        return pick_image(manifest, category, exclude_review=False)
    return None


def pick_image_any(manifest, exclude_review=True):
    """Fallback for the carousel mix when a specific category has run out —
    picks any unused image regardless of category."""
    for entry in manifest["images"]:
        if entry["used"] or entry.get("excluded"):
            continue
        if exclude_review and entry.get("needs_review"):
            continue
        return entry
    if exclude_review:
        return pick_image_any(manifest, exclude_review=False)
    return None


def mark_used(entry):
    entry["used"] = True
    entry["used_at"] = datetime.datetime.now().isoformat(timespec="seconds")


def cmd_story():
    manifest = load_manifest()
    picks = {}
    for cat in ("prato_salgado", "salada", "doce"):
        entry = pick_image(manifest, cat)
        if entry is None:
            print(f"ERRO: sem imagens disponiveis na categoria {cat}.", file=sys.stderr)
            raise SystemExit(1)
        picks[cat] = entry

    for entry in picks.values():
        mark_used(entry)
    save_manifest(manifest)

    for cat in ("prato_salgado", "salada", "doce"):
        print(picks[cat]["converted_path"])


FEED_CAROUSEL_MIX = ["prato_salgado", "prato_salgado", "salada", "doce", "ambiente"]


def cmd_feed():
    manifest = load_manifest()
    picks = []
    for cat in FEED_CAROUSEL_MIX:
        entry = pick_image(manifest, cat) or pick_image_any(manifest)
        if entry is None:
            print(f"ERRO: sem imagens disponiveis pra completar o carrossel (faltou categoria {cat}).", file=sys.stderr)
            raise SystemExit(1)
        mark_used(entry)  # mark immediately so the next pick in this same run doesn't grab it again
        picks.append(entry)

    save_manifest(manifest)
    for entry in picks:
        print(entry["converted_path"])


def cmd_reel():
    data = load_video_manifest()

    for entry in data["videos"]:
        if entry["used"] or entry.get("too_short") or entry.get("silent"):
            continue

        if entry.get("duration_seconds") is None:
            try:
                entry["duration_seconds"] = get_video_duration_seconds(entry["path"])
            except Exception as e:
                print(f"AVISO: nao consegui ler duracao de {entry['path']}: {e}", file=sys.stderr)
                entry["too_short"] = True  # treat unreadable videos as unusable too
                save_video_manifest(data)
                continue
            entry["too_short"] = entry["duration_seconds"] <= MIN_REEL_DURATION_SECONDS
            save_video_manifest(data)  # cache the probed duration even if we don't pick this one
        if entry["too_short"]:
            continue

        if entry.get("audio_mean_db") is None:
            try:
                entry["audio_mean_db"] = get_audio_mean_volume_db(entry["path"])
            except Exception as e:
                print(f"AVISO: nao consegui ler audio de {entry['path']}: {e}", file=sys.stderr)
                entry["silent"] = True  # no readable audio stream = treat as silent
                save_video_manifest(data)
                continue
            entry["silent"] = entry["audio_mean_db"] <= MIN_REEL_AUDIO_DB
            save_video_manifest(data)
        if entry["silent"]:
            continue

        entry["used"] = True
        entry["used_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        save_video_manifest(data)
        print(entry["path"])
        return

    print(f"ERRO: nenhum video disponivel com mais de {MIN_REEL_DURATION_SECONDS}s e com audio audivel pra reel.", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("story", "feed", "reel"):
        print("Uso: select_media.py story|feed|reel", file=sys.stderr)
        raise SystemExit(1)
    {"story": cmd_story, "feed": cmd_feed, "reel": cmd_reel}[sys.argv[1]]()
