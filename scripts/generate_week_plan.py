#!/usr/bin/env python3
"""Generates next week's full posting plan (feed Tue/Thu, stories Mon-Fri,
reel Mon) WITHOUT posting anything -- selects + reserves media and generates
captions ahead of time, so the whole week can be reviewed and approved as one
batch before the scheduled poller is allowed to actually publish anything.

Usage: generate_week_plan.py
Writes content/week_plans/<monday-date>.json (status: "pending_approval").
Prints the plan file path.
"""
import datetime
import json
import os
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLANS_DIR = os.path.join(PROJECT_DIR, "content", "week_plans")

WEEKDAY_NAMES = {0: "segunda", 1: "terca", 2: "quarta", 3: "quinta", 4: "sexta"}


def run(cmd):
    # PYTHONIOENCODING forces UTF-8 on the child's stdout regardless of the
    # Windows console codepage -- without it, accented paths (Agência,
    # Vídeos...) get written in cp1252 and this decode as utf-8 blows up.
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    if result.returncode != 0:
        print(f"ERRO rodando {cmd}:\n{result.stderr}", file=sys.stderr)
        raise SystemExit(1)
    return result.stdout.strip()


def python(script_rel, *args):
    return run([sys.executable, os.path.join(SCRIPTS_DIR, script_rel), *args])


def next_monday():
    today = datetime.date.today()
    days_ahead = (7 - today.weekday()) % 7 or 7
    return today + datetime.timedelta(days=days_ahead)


def build_story_post(date):
    lines = python("select_brenda_story.py", WEEKDAY_NAMES[date.weekday()]).splitlines()
    items = []
    for line in lines:
        category, type_, path = line.split("\t")
        items.append({"category": category, "type": type_, "path": path})
    return {"date": date.isoformat(), "weekday": WEEKDAY_NAMES[date.weekday()], "slot": "story", "items": items}


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_feed_post(date):
    paths = python("select_media.py", "feed").splitlines()
    caption_file = python("caption_from_photo.py", "feed", *paths)
    return {
        "date": date.isoformat(), "weekday": WEEKDAY_NAMES[date.weekday()], "slot": "feed",
        "items": [{"type": "image", "path": p} for p in paths],
        # caption_text is authoritative and portable (embedded in the plan
        # itself); caption_file is local-machine-only (content/caption_*.txt
        # is gitignored) and kept only for local debugging reference.
        "caption_file": caption_file,
        "caption_text": _read_text(caption_file),
    }


def build_reel_post(date):
    path = python("select_media.py", "reel")
    caption_file = python("caption_for_reel.py", path)
    return {
        "date": date.isoformat(), "weekday": WEEKDAY_NAMES[date.weekday()], "slot": "reel",
        "items": [{"type": "video", "path": path}],
        "caption_file": caption_file,
        "caption_text": _read_text(caption_file),
    }


def main():
    monday = next_monday()
    posts = []
    for i in range(5):
        date = monday + datetime.timedelta(days=i)
        print(f"Gerando story de {date} ({WEEKDAY_NAMES[date.weekday()]})...", file=sys.stderr)
        posts.append(build_story_post(date))
        if date.weekday() == 0:  # segunda -> reel
            print(f"Gerando reel de {date}...", file=sys.stderr)
            posts.append(build_reel_post(date))
        if date.weekday() in (1, 3):  # terca/quinta -> feed
            print(f"Gerando feed de {date}...", file=sys.stderr)
            posts.append(build_feed_post(date))

    plan = {
        "week_start": monday.isoformat(),
        "status": "pending_approval",
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "posts": posts,
    }

    os.makedirs(PLANS_DIR, exist_ok=True)
    plan_path = os.path.join(PLANS_DIR, f"{monday.isoformat()}.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(plan_path)


if __name__ == "__main__":
    main()
