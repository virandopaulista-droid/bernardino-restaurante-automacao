#!/usr/bin/env python3
"""Picks today's 3 Brenda-Stories assets (prato do dia / salada / doce) from
content/brenda_stories_manifest.json and marks them used.

Selection per slot: prefer an unused asset tagged with today's weekday in
that category; if none left, fall back to the generic (weekday=null) pool
for that category. If a pool (weekday-specific OR generic) runs out of
unused assets, it auto-resets (all its assets marked unused again) so the
rotation never stalls — this folder doesn't grow daily like the client's
real photo library does.

Usage: select_brenda_story.py [segunda|terca|quarta|quinta|sexta]
  (defaults to today's actual weekday; only Mon-Fri are valid)
Prints 3 lines: category<TAB>type<TAB>absolute_path
"""
import datetime
import json
import os
import random
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(PROJECT_DIR, "content", "brenda_stories_manifest.json")
# Windows default kept for local runs; GitHub Actions sets BRENDA_STORIES_DIR
# to the rclone-mounted path instead (no G:\ drive there).
ASSETS_DIR = os.environ.get(
    "BRENDA_STORIES_DIR",
    r"G:\Meu Drive\Agência BEEF MTK\Clientes\Bernadino restaurante\STORIES\Brenda - Stories",
)

WEEKDAY_MAP = {0: "segunda", 1: "terca", 2: "quarta", 3: "quinta", 4: "sexta"}


def load():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save(data):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pick(assets, category, weekday):
    pool = [a for a in assets if a["category"] == category and a["weekday"] == weekday and not a["used"]]
    if not pool:
        # try the other pool (day-specific vs generic) before resetting anything
        return None
    return random.choice(pool)


def pick_for_slot(data, category, weekday):
    assets = data["assets"]
    entry = pick(assets, category, weekday) if weekday else None
    if entry is None:
        entry = pick(assets, category, None)
    if entry is None:
        # both pools exhausted (or the weekday-specific one never had unused
        # items) -- reset the generic pool for this category and retry
        for a in assets:
            if a["category"] == category and a["weekday"] is None:
                a["used"] = False
        entry = pick(assets, category, None)
    if entry is None and weekday:
        # weekday-specific pool exhausted too -- reset it and retry
        for a in assets:
            if a["category"] == category and a["weekday"] == weekday:
                a["used"] = False
        entry = pick(assets, category, weekday)
    if entry is None:
        raise SystemExit(f"ERRO: nenhum asset disponivel para categoria={category}")
    entry["used"] = True
    entry["used_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    return entry


def main():
    if len(sys.argv) > 1:
        weekday = sys.argv[1]
        if weekday not in WEEKDAY_MAP.values():
            print("Uso: select_brenda_story.py [segunda|terca|quarta|quinta|sexta]", file=sys.stderr)
            raise SystemExit(1)
    else:
        wd_num = datetime.datetime.now().weekday()
        if wd_num not in WEEKDAY_MAP:
            print("ERRO: hoje e fim de semana, sem story agendado.", file=sys.stderr)
            raise SystemExit(1)
        weekday = WEEKDAY_MAP[wd_num]

    data = load()
    picks = []
    for category in ("salgado", "salada", "doce"):
        entry = pick_for_slot(data, category, weekday)
        picks.append(entry)
    save(data)

    for entry in picks:
        abs_path = os.path.join(ASSETS_DIR, entry["file"])
        print(f"{entry['category']}\t{entry['type']}\t{abs_path}")


if __name__ == "__main__":
    main()
