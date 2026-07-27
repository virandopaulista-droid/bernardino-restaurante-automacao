#!/usr/bin/env python3
"""Merges the new Brenda-Stories videos into brenda_stories_manifest.json.

Weekday comes from the OCR report (brenda_video_ocr_report.json) -- only
trusted when OCR actually found a weekday keyword; otherwise null (generic,
any day), same convention as the hand-classified images.

Category comes from: the OCR report's category_guess if it found one
(literal text match, e.g. "DOCES"/"SALADAS" on screen -- high confidence);
otherwise the CLIP visual classifier (scripts/clip_classifier.py, already
used and validated on ~1200 real photos this project) run on a mid-video
frame. If CLIP says "ambiente" or "outro" (not a salgado/salada/doce shot),
the video is excluded from the 3 rotation categories and flagged for human
review rather than guessed into a category it doesn't belong in.

Usage: merge_brenda_videos.py
Writes an updated brenda_stories_manifest.json and prints a summary.
"""
import json
import os
import subprocess
import sys
import tempfile

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_DIR, "scripts"))
import clip_classifier  # noqa: E402

ASSETS_DIR = r"G:\Meu Drive\Agência BEEF MTK\Clientes\Bernadino restaurante\STORIES\Brenda - Stories"
MANIFEST_PATH = os.path.join(PROJECT_DIR, "content", "brenda_stories_manifest.json")
OCR_REPORT_PATH = os.path.join(PROJECT_DIR, "content", "brenda_video_ocr_report.json")

CLIP_TO_MANIFEST = {"prato_salgado": "salgado", "salada": "salada", "doce": "doce"}


def extract_frame(video_path, out_jpg, timestamp=2.5):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path, "-frames:v", "1", out_jpg, "-loglevel", "error"],
        check=False,
    )
    return os.path.exists(out_jpg)


def main():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(OCR_REPORT_PATH, "r", encoding="utf-8") as f:
        ocr_report = {r["file"]: r for r in json.load(f)}

    known_files = {a["file"] for a in manifest["assets"]}
    new_files = [f for f in ocr_report if f not in known_files]

    added, excluded = [], []
    with tempfile.TemporaryDirectory() as tmp:
        frame_path = os.path.join(tmp, "frame.jpg")
        for i, fname in enumerate(new_files, 1):
            ocr_entry = ocr_report[fname]
            weekday = ocr_entry["weekday_guess"]
            category = ocr_entry["category_guess"]
            clip_conf = None

            if category is None:
                video_path = os.path.join(ASSETS_DIR, fname)
                if os.path.exists(frame_path):
                    os.remove(frame_path)
                if extract_frame(video_path, frame_path):
                    clip_label, clip_conf = clip_classifier.classify(frame_path)
                    category = CLIP_TO_MANIFEST.get(clip_label)  # None if ambiente/outro

            entry = {
                "file": fname, "type": "video", "used": False, "used_at": None,
                "category": category, "weekday": weekday,
                "classified_by": "ocr" if ocr_entry["category_guess"] else "clip",
                "clip_confidence": clip_conf,
            }
            if category is None:
                entry["excluded"] = True
                entry["exclude_reason"] = "sem categoria confiavel (nem OCR nem CLIP bateram em salgado/salada/doce)"
                excluded.append(entry)
            else:
                added.append(entry)

            if i % 20 == 0:
                print(f"[{i}/{len(new_files)}] processado...", file=sys.stderr)

    manifest["assets"].extend(added)
    manifest["assets"].extend(excluded)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    by_weekday = {}
    for e in added:
        by_weekday.setdefault(e["weekday"] or "generico", []).append(e["category"])
    print(f"\n{len(added)} videos adicionados, {len(excluded)} excluidos (sem categoria confiavel).")
    for wd, cats in sorted(by_weekday.items()):
        print(f"  {wd}: {len(cats)} (salgado={cats.count('salgado')} salada={cats.count('salada')} doce={cats.count('doce')})")
    if excluded:
        print("\nExcluidos (revisar manualmente se quiser usa-los):")
        for e in excluded:
            print(f"  {e['file']}")


if __name__ == "__main__":
    main()
