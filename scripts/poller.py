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
  Mon-Fri 7:00  -> story
  Mon 9:00      -> reel

Catch-up, not a narrow window: fires as soon as "now" is at or past a
scheduled time (same day), and keeps trying on every later tick until that
slot's "posted" flag is set -- GitHub's own cron schedule has proven
unreliable about landing near its configured time (confirmed 2026-07-29,
see memory), so a narrow match window caused entire days to silently post
nothing. Each individual post in the plan tracks its own "posted" flag (in
the plan JSON itself) so repeated ticks the same day don't double-post.

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

# weekday(): Monday=0 ... Sunday=6
SCHEDULE = [
    {"slot": "feed", "weekdays": {1, 3}, "hour": 10, "minute": 0},   # Tue, Thu
    {"slot": "story", "weekdays": {0, 1, 2, 3, 4}, "hour": 7, "minute": 0},  # Mon-Fri
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
        # NAO usar SystemExit aqui -- SystemExit nao e subclasse de Exception,
        # entao o "except Exception" no loop principal (que aciona
        # handle_partial_failure e marca posted=True pra nunca reenviar o que
        # ja saiu) nunca capturava isso. Resultado real, confirmado
        # 2026-08-13: post_instagram.sh falhou, o processo morreu sem marcar
        # posted=True, e a proxima tentativa duplicou o post do Facebook que
        # ja tinha saido com sucesso na primeira. RuntimeError e capturado
        # normalmente pelo except Exception.
        raise RuntimeError(f"comando falhou (exit {result.returncode}): {cmd}")
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
        # Ver comentario equivalente em run() acima -- SystemExit nao e
        # subclasse de Exception, entao usa-lo aqui faz o "except Exception"
        # do loop principal nunca acionar a protecao contra post duplicado.
        raise RuntimeError(f"comando falhou (exit {result.returncode}): {script_rel}")
    return result.stdout.strip()


PATH_ANCHORS = [
    ("Imagens tratadas", lambda: os.path.dirname(os.environ.get("MEDIA_DIR_IMAGES_2025", ""))),
    ("Vídeos Tratados", lambda: os.environ.get("MEDIA_DIR_VIDEOS", "")),
    ("Brenda - Stories", lambda: os.environ.get("BRENDA_STORIES_DIR", "")),
]


def _find_by_normalized_name(dir_path, target_name):
    """Directory listing + NFC-normalized comparison, instead of a direct
    path stat -- an accented filename (TERÇA, Vídeos...) written on Windows
    and a Linux/rclone FUSE mount can represent the same character with
    different Unicode normalization forms, so a literal path string that
    LOOKS identical can still fail os.path.exists()."""
    import unicodedata
    target_norm = unicodedata.normalize("NFC", target_name)
    try:
        entries = os.listdir(dir_path)
    except OSError:
        return None
    for entry in entries:
        if unicodedata.normalize("NFC", entry) == target_norm:
            return os.path.join(dir_path, entry)
    return None


def resolve_path(path):
    """A week plan can be generated on one machine (local Windows, G:\\...)
    and posted from another (GitHub Actions' Linux rclone mount) -- if the
    stored absolute path doesn't exist here, rebuild it from a known anchor
    folder name plus this environment's own MEDIA_DIR_*/BRENDA_STORIES_DIR,
    then match the filename by normalized comparison (see
    _find_by_normalized_name)."""
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
        found = _find_by_normalized_name(os.path.dirname(candidate), os.path.basename(candidate))
        if found:
            return found
    return path  # unchanged -- let the caller's own error surface if still missing


def resolve_caption_file(post):
    """caption_text (embedded in the plan) is authoritative and portable;
    caption_file is a local-machine-only path (content/caption_*.txt is
    gitignored, so a plan generated on one machine has no such file on
    another) -- write caption_text to a fresh temp file here instead of
    trusting the stored path. Falls back to caption_file for older plans
    that predate caption_text."""
    if post.get("caption_text"):
        import tempfile
        fd, path = tempfile.mkstemp(prefix="caption_live_", suffix=".txt", dir=os.path.join(PROJECT_DIR, "content"))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(post["caption_text"])
        return path
    return post["caption_file"]


def notify_once(marker, body):
    """Opens a GitHub Issue so a missing/unapproved plan is actually visible
    somewhere a human might see it, instead of only in a log nobody reads --
    guarded by `marker` so repeated ticks the same day/situation don't spam
    a new issue every 15 minutes. Best-effort: never raises, a notification
    failure must not crash the poller."""
    try:
        title = f"[poller] {marker}"
        check = subprocess.run(
            ["gh", "issue", "list", "--search", f'"{title}" in:title', "--state", "open", "--json", "number"],
            capture_output=True, text=True,
        )
        if check.returncode == 0 and check.stdout.strip() and check.stdout.strip() != "[]":
            return  # already have an open issue for this exact situation
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", body], capture_output=True, text=True)
    except Exception as e:
        print(f"AVISO: notify_once falhou (nao critico): {e}", file=sys.stderr)


def handle_partial_failure(post, plan, plan_path, now, slot_label, exc):
    """A handler crashed mid-posting (e.g. one of several items in a story
    failed via the FB/IG API partway through). Some items may have posted
    for real and some may not have -- there's no structural way to tell
    which from here, since the posting scripts don't report per-item
    progress back to this process. Marking "posted" unconditionally is the
    safer failure mode: it stops the next tick from blindly re-running the
    whole handler and re-posting whatever already went out for real
    (confirmed happening 2026-08-05: a story's first item posted
    successfully, the second item hit an API error and crashed the script
    before "posted" was set, so the next tick re-posted all 3 items,
    duplicating the first). A human has to check Facebook/Instagram
    directly and manually post anything that's actually missing -- that
    can't be determined automatically from a crash alone."""
    print(f"##[error] Falha ao publicar '{slot_label}': {exc}", file=sys.stderr)
    post["posted"] = True
    post["posted_at"] = now.isoformat(timespec="seconds")
    post["posting_error"] = f"Falha parcial/total ao publicar -- verificar manualmente o que saiu de verdade. Erro: {exc}"
    save_plan(plan, plan_path)
    notify_once(
        f"post-falhou-{post.get('date')}-{post.get('slot')}",
        f"O poller tentou publicar '{slot_label}' ({post.get('date')}) e um erro interrompeu a publicacao no meio "
        "(alguns itens podem ter saido de verdade, outros nao -- nao da pra saber automaticamente qual). "
        "Para nao arriscar duplicar o que ja saiu, marquei esse post como 'posted:true' -- ele NAO sera tentado de "
        "novo automaticamente. Confira manualmente no Facebook/Instagram do Bernardino o que realmente foi "
        f"publicado, e publique manualmente qualquer item que estiver faltando.\n\nErro original: {exc}"
    )


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
    caption_file = resolve_caption_file(post)
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
    # trailing \n is required -- bash's `while read` returns non-zero (and
    # skips the loop body) for a final line with no terminating newline, so
    # without it the LAST item silently never gets processed (found via a
    # real live test 2026-07-27: the 3rd story item, always a video, kept
    # silently not posting no matter what else was fixed).
    lines = "\n".join(f"{it['category']}\t{it['type']}\t{resolve_path(it['path'])}" for it in post["items"]) + "\n"
    if DRY_RUN:
        print(f"[DRY-RUN] 3 stories (salgado/salada/doce): {[it['path'] for it in post['items']]}")
        return
    print(bash_stdin("post_brenda_story_items.sh", lines))


def handle_reel(post):
    path = resolve_path(post["items"][0]["path"])
    caption_file = resolve_caption_file(post)
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
        try:
            HANDLERS[force_slot](post)
        except Exception as exc:
            if not DRY_RUN:
                handle_partial_failure(post, plan, plan_path, now, force_slot, exc)
            raise
        if not DRY_RUN:
            post["posted"] = True
            post["posted_at"] = now.isoformat(timespec="seconds")
            save_plan(plan, plan_path)
        return

    for entry in SCHEDULE:
        if now.weekday() not in entry["weekdays"]:
            continue
        scheduled = now.replace(hour=entry["hour"], minute=entry["minute"], second=0, microsecond=0)
        # Catch-up, not a narrow window: GitHub's cron has proven unreliable
        # about firing at the exact configured time (confirmed 2026-07-29 --
        # a "schedule"-triggered run landed hours off target and matched no
        # window, so nothing posted all day). So: fire as soon as we're AT
        # OR PAST the scheduled time, and keep firing on every later tick
        # THE SAME DAY until "posted" is set -- whichever tick actually
        # lands after the target time catches it, instead of requiring one
        # to land within a specific narrow band.
        if now < scheduled:
            continue

        monday = week_monday(now.date())
        plan, plan_path = load_plan(monday)
        if plan is None:
            msg = f"AVISO: nenhum cronograma encontrado pra semana de {monday} ({plan_path})."
            print(msg, file=sys.stderr)
            if not DRY_RUN:
                notify_once(f"cronograma-ausente-{monday}", msg + " Rode generate_week_plan.py e aprove.")
            return
        if plan["status"] != "approved":
            msg = f"AVISO: cronograma da semana de {monday} ainda esta '{plan['status']}', nao aprovado."
            print(msg, file=sys.stderr)
            if not DRY_RUN:
                notify_once(f"cronograma-nao-aprovado-{monday}", msg + " Nada sera postado ate ser aprovado.")
            return

        post = next((p for p in plan["posts"] if p["date"] == today_key and p["slot"] == entry["slot"]), None)
        if post is None:
            print(f"AVISO: cronograma aprovado nao tem post de '{entry['slot']}' pra hoje ({today_key}).", file=sys.stderr)
            return
        if post.get("posted"):
            return  # already posted this window, avoid duplicate on the next 5-min tick

        print(f"Disparando slot '{entry['slot']}' ({'DRY-RUN' if DRY_RUN else 'LIVE'})...")
        try:
            HANDLERS[entry["slot"]](post)
        except Exception as exc:
            if not DRY_RUN:
                handle_partial_failure(post, plan, plan_path, now, entry["slot"], exc)
            raise

        if not DRY_RUN:
            post["posted"] = True
            post["posted_at"] = now.isoformat(timespec="seconds")
            save_plan(plan, plan_path)
        return

    print("Nenhum slot agendado agora.")


if __name__ == "__main__":
    main()
