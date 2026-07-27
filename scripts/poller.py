#!/usr/bin/env python3
"""Checks whether now matches a scheduled Bernardino Restaurante slot and, if
so, publishes the corresponding post from THIS WEEK'S APPROVED PLAN. Meant to
be invoked every few minutes by Windows Task Scheduler during the relevant
windows.

Nothing is selected or captioned here anymore -- that all happens ahead of
time in generate_week_plan.py, reviewed as a gallery (build_week_gallery.py),
and explicitly approved (approve_week_plan.py) by the user. If this week's
plan is missing or still "pending_approval", the poller refuses to post and
just warns -- there is no fallback to auto-selecting/posting unreviewed
content. See memory/bernardino-restaurante-automation.md for why.

Schedule (see docs/guia-bernardino.md):
  Tue/Thu 10:00 -> feed
  Mon-Fri 8:00  -> story
  Mon 9:00      -> reel

Matches a slot if now is within WINDOW_MINUTES of the scheduled time. Each
individual post in the plan tracks its own "posted" flag (in the plan JSON
itself) so re-running within the same window doesn't double-post.

Defaults to --dry-run (prints what it would do, does NOT call Facebook).
Pass --live to actually publish.
"""
import datetime
import json
import os
import subprocess
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PLANS_DIR = os.path.join(PROJECT_DIR, "content", "week_plans")
VIDEOS_FOLDER_MAP_PATH = os.path.join(PROJECT_DIR, "content", "videos_drive_folder_map.json")

WINDOW_MINUTES = 10

# weekday(): Monday=0 ... Sunday=6
SCHEDULE = [
    {"slot": "feed", "weekdays": {1, 3}, "hour": 10, "minute": 0},   # Tue, Thu
    {"slot": "story", "weekdays": {0, 1, 2, 3, 4}, "hour": 8, "minute": 0},  # Mon-Fri
    {"slot": "reel", "weekdays": {0}, "hour": 9, "minute": 0},        # Mon
]

DRY_RUN = "--live" not in sys.argv[1:]


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


def bash(script_rel, *args):
    return run(["bash", os.path.join(SCRIPTS_DIR, script_rel), *args])


def python(script_rel, *args):
    return run([sys.executable, os.path.join(SCRIPTS_DIR, script_rel), *args])


def bash_stdin(script_rel, stdin_text):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    result = subprocess.run(
        ["bash", os.path.join(SCRIPTS_DIR, script_rel)],
        input=stdin_text, capture_output=True, text=True, encoding="utf-8", env=env,
    )
    if result.returncode != 0:
        print(f"ERRO rodando {script_rel}:\n{result.stderr}", file=sys.stderr)
        raise SystemExit(1)
    return result.stdout.strip()


PATH_ANCHORS = [
    ("Imagens tratadas", lambda: os.path.dirname(os.environ.get("MEDIA_DIR_IMAGES_2025", ""))),
    ("Vídeos Tratados", lambda: os.environ.get("MEDIA_DIR_VIDEOS", "")),
    ("Brenda - Stories", lambda: os.environ.get("BRENDA_STORIES_DIR", "")),
]


def resolve_path(path):
    """A week plan can be generated on one machine (local Windows, G:\\...)
    and posted from another (GitHub Actions' Linux rclone mount) -- if the
    stored absolute path doesn't exist here, rebuild it from a known anchor
    folder name plus this environment's own MEDIA_DIR_*/BRENDA_STORIES_DIR."""
    if os.path.exists(path):
        return path
    normalized = path.replace("\\", "/")
    for anchor, get_base in PATH_ANCHORS:
        idx = normalized.find(anchor)
        if idx == -1:
            continue
        base = get_base()
        if not base:
            continue
        remainder = normalized[idx + len(anchor):].lstrip("/")
        candidate = os.path.join(base, remainder)
        if os.path.exists(candidate):
            return candidate
    return path  # unchanged -- let the caller's own error surface if still missing


def week_monday(date):
    return date - datetime.timedelta(days=date.weekday())


def load_plan(monday):
    plan_path = os.path.join(PLANS_DIR, f"{monday.isoformat()}.json")
    if not os.path.exists(plan_path):
        return None, plan_path
    with open(plan_path, encoding="utf-8") as f:
        return json.load(f), plan_path


def save_plan(plan, plan_path):
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)


def handle_feed(post):
    paths = [resolve_path(it["path"]) for it in post["items"]]
    caption_file = post["caption_file"]
    if DRY_RUN:
        with open(caption_file, encoding="utf-8") as f:
            print(f"[DRY-RUN] carrossel de feed com {paths}\nLegenda:\n{f.read()}")
        return

    fb_output = bash("post_bernardino.sh", caption_file, "now", *paths)
    print(fb_output)

    ig_business_id = os.environ.get("IG_BUSINESS_ID", "").strip()
    if not ig_business_id:
        print("Instagram pulado (IG_BUSINESS_ID nao configurado ainda).")
        return

    photo_urls = []
    for line in fb_output.splitlines():
        if line.startswith("PHOTO_URLS:"):
            photo_urls = json.loads(line[len("PHOTO_URLS:"):])
    if not photo_urls:
        print("AVISO: sem URL publica de foto, pulando Instagram.", file=sys.stderr)
        return
    print(bash("post_instagram.sh", caption_file, *photo_urls))


def handle_story(post):
    lines = "\n".join(f"{it['category']}\t{it['type']}\t{resolve_path(it['path'])}" for it in post["items"])
    if DRY_RUN:
        print(f"[DRY-RUN] 3 stories (salgado/salada/doce): {[it['path'] for it in post['items']]}")
        return
    print(bash_stdin("post_brenda_story_items.sh", lines))


def handle_reel(post):
    path = resolve_path(post["items"][0]["path"])
    caption_file = post["caption_file"]
    if DRY_RUN:
        print(f"[DRY-RUN] reel com video: {path}")
        return

    print(bash("post_reel_fb.sh", path, caption_file))

    ig_business_id = os.environ.get("IG_BUSINESS_ID", "").strip()
    if not ig_business_id:
        print("Instagram pulado (IG_BUSINESS_ID nao configurado ainda).")
        return

    month_folder = os.path.basename(os.path.dirname(path))
    with open(VIDEOS_FOLDER_MAP_PATH, encoding="utf-8") as f:
        folder_map = json.load(f)["folders"]
    folder_id = folder_map.get(month_folder)
    if not folder_id:
        print(f"AVISO: pasta '{month_folder}' nao tem ID publico mapeado, pulando Instagram.", file=sys.stderr)
        return

    fname = os.path.basename(path)
    video_url = python("resolve_drive_url.py", fname, folder_id)
    print(bash("post_reel_instagram.sh", caption_file, video_url))


HANDLERS = {"feed": handle_feed, "story": handle_story, "reel": handle_reel}


def _arg_value(flag):
    args = sys.argv[1:]
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    return None


def main():
    now = datetime.datetime.now()
    today_key = now.strftime("%Y-%m-%d")

    force_date = _arg_value("--force-date")
    force_slot = _arg_value("--force-slot")
    if force_date and force_slot:
        # Bypasses the schedule/time-window check entirely -- for manual
        # verification runs only (e.g. "does this actually reach FB/IG"),
        # never used by the real cron-triggered firings.
        print(f"FORCE: postando '{force_slot}' de {force_date} agora, ignorando janela de horario...")
        monday = week_monday(datetime.date.fromisoformat(force_date))
        plan, plan_path = load_plan(monday)
        if plan is None or plan["status"] != "approved":
            print("AVISO: cronograma nao encontrado ou nao aprovado.", file=sys.stderr)
            return
        post = next((p for p in plan["posts"] if p["date"] == force_date and p["slot"] == force_slot), None)
        if post is None:
            print(f"AVISO: nao ha post de '{force_slot}' em {force_date} no cronograma.", file=sys.stderr)
            return
        if post.get("posted"):
            print("AVISO: esse post ja foi marcado como publicado antes.", file=sys.stderr)
            return
        HANDLERS[force_slot](post)
        if not DRY_RUN:
            post["posted"] = True
            post["posted_at"] = now.isoformat(timespec="seconds")
            save_plan(plan, plan_path)
        return

    for entry in SCHEDULE:
        if now.weekday() not in entry["weekdays"]:
            continue
        scheduled = now.replace(hour=entry["hour"], minute=entry["minute"], second=0, microsecond=0)
        delta_minutes = abs((now - scheduled).total_seconds()) / 60
        if delta_minutes > WINDOW_MINUTES:
            continue

        monday = week_monday(now.date())
        plan, plan_path = load_plan(monday)
        if plan is None:
            print(f"AVISO: nenhum cronograma encontrado pra semana de {monday} ({plan_path}). "
                  "Rode generate_week_plan.py e aprove antes do horario de postagem.", file=sys.stderr)
            return
        if plan["status"] != "approved":
            print(f"AVISO: cronograma da semana de {monday} ainda esta '{plan['status']}', "
                  "nao aprovado. Nao vou postar nada ate ser aprovado.", file=sys.stderr)
            return

        post = next((p for p in plan["posts"] if p["date"] == today_key and p["slot"] == entry["slot"]), None)
        if post is None:
            print(f"AVISO: cronograma aprovado nao tem post de '{entry['slot']}' pra hoje ({today_key}).", file=sys.stderr)
            return
        if post.get("posted"):
            return  # already posted this window, avoid duplicate on the next 5-min tick

        print(f"Disparando slot '{entry['slot']}' ({'DRY-RUN' if DRY_RUN else 'LIVE'})...")
        HANDLERS[entry["slot"]](post)

        if not DRY_RUN:
            post["posted"] = True
            post["posted_at"] = now.isoformat(timespec="seconds")
            save_plan(plan, plan_path)
        return

    print("Nenhum slot agendado agora.")


if __name__ == "__main__":
    main()
