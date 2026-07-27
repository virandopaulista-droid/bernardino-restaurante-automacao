#!/usr/bin/env python3
"""Bulk-classifies the new Brenda-Stories videos by OCR: extracts a mid-video
frame with ffmpeg, runs Tesseract (Portuguese) on it, and matches known
weekday/category keywords -- the same baked-in-text convention already
confirmed by hand for the ~85 image assets (see brenda_stories_manifest.json).

Usage: ocr_classify_videos.py
Writes content/brenda_video_ocr_report.json: one entry per new video with the
raw OCR text + a best-guess weekday/category + a confidence flag, for human
review before merging into brenda_stories_manifest.json.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ASSETS_DIR = r"G:\Meu Drive\Agência BEEF MTK\Clientes\Bernadino restaurante\STORIES\Brenda - Stories"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(PROJECT_DIR, "content", "brenda_stories_manifest.json")
REPORT_PATH = os.path.join(PROJECT_DIR, "content", "brenda_video_ocr_report.json")

TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = os.environ.get(
    "TESSDATA_PREFIX",
    r"C:\Users\Robso\AppData\Local\Temp\claude\C--Users-Robso-cloude\1afaab22-a749-4751-9121-1d44b1412dfe\scratchpad\tessdata",
)

WEEKDAY_PATTERNS = {
    "segunda": [r"\bSEGUNDA\b", r"\bSEGUNDOU\b"],
    "terca": [r"\bTER[ÇC]A\b"],
    "quarta": [r"\bQUARTA\b", r"\bFEIJOADA\b"],
    "quinta": [r"\bQUINTA\b", r"\bMASSAS?\b", r"\bNHOQUE\b", r"\bGNOCCHI\b"],
    "sexta": [r"\bSEXTA\b", r"\bSALM[ÃA]O\b"],
}
CATEGORY_PATTERNS = {
    "doce": [r"\bDOCE\b", r"\bDOCES\b", r"\bSOBREMESAS?\b", r"\bA[CÇ]UCAR\b", r"\bA[DÇ]O[ÇC]AR\b", r"\bPAUSA DOCE\b"],
    "salada": [r"\bSALADAS?\b", r"\bFRESC[ao]S?\b", r"\bLEVEZA\b", r"\bNUTRITIV"],
    "salgado": [r"\bBUFFET\b", r"\bPRATO\b", r"\bSABOR\b", r"\bTRADI[ÇC][ÃA]O\b", r"\bFRUTOS DO MAR\b", r"\bPEIXES?\b", r"\bFRANGO\b"],
}


def already_known_files():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {a["file"] for a in data["assets"]}


FRAME_TIMESTAMPS = [0.3, 1.0, 1.8, 2.6, 3.4, 4.2, 4.8]


def extract_frame(video_path, timestamp, out_jpg):
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(timestamp), "-i", video_path, "-frames:v", "1", out_jpg, "-loglevel", "error"],
        check=False,
    )
    return os.path.exists(out_jpg)


def ocr(jpg_path):
    env = dict(os.environ, TESSDATA_PREFIX=TESSDATA_DIR)
    result = subprocess.run(
        [TESSERACT, jpg_path, "stdout", "-l", "por"],
        capture_output=True, text=True, env=env, encoding="utf-8", errors="replace",
    )
    return result.stdout.upper()


def ocr_video_multi(video_path, tmp_dir):
    combined = []
    frame_path = os.path.join(tmp_dir, "frame.jpg")
    for ts in FRAME_TIMESTAMPS:
        if os.path.exists(frame_path):
            os.remove(frame_path)
        if extract_frame(video_path, ts, frame_path):
            text = ocr(frame_path)
            if text.strip():
                combined.append(text)
    if os.path.exists(frame_path):
        os.remove(frame_path)
    return " \n ".join(combined)


def classify_text(text):
    weekday = None
    for wd, patterns in WEEKDAY_PATTERNS.items():
        if any(re.search(p, text) for p in patterns):
            weekday = wd
            break
    category = None
    for cat, patterns in CATEGORY_PATTERNS.items():
        if any(re.search(p, text) for p in patterns):
            category = cat
            break
    return weekday, category


def main():
    known = already_known_files()
    all_videos = sorted(f for f in os.listdir(ASSETS_DIR) if f.lower().endswith(".mp4"))
    new_videos = [f for f in all_videos if f not in known]
    print(f"{len(all_videos)} videos no total, {len(new_videos)} novos (nao classificados ainda).", file=sys.stderr)

    report = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, fname in enumerate(new_videos, 1):
            video_path = os.path.join(ASSETS_DIR, fname)
            text = ocr_video_multi(video_path, tmp)
            weekday, category = classify_text(text)
            report.append({
                "file": fname,
                "ocr_text": " ".join(text.split()),
                "weekday_guess": weekday,
                "category_guess": category,
                "confident": bool(weekday or category),
            })
            print(f"[{i}/{len(new_videos)}] {fname}: weekday={weekday} category={category}", file=sys.stderr)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"Relatorio salvo em {REPORT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
