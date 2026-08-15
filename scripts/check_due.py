#!/usr/bin/env python3
"""Fast, Drive-free pre-check used by poller.yml as an early-exit gate:
prints DUE (exit 0) if a story/feed/reel slot looks like it needs posting
right now, or NOT_DUE (exit 1) otherwise, so the workflow can skip the
expensive rclone/Drive-mount steps on the majority of ticks where nothing
is actually due (cron-job.org + GitHub's own schedule both fire every ~15
min, but a real slot only becomes due a handful of times a day).

Deliberately conservative and fully independent from poller.py's own
matching logic (never imports it, never touches the Drive, never writes
anything) -- worst case if this check is ever wrong: a wasted mount (same
cost as before this existed) or a post delayed to the next ~15-min tick,
since poller.py's real logic (unchanged) is still the actual authority on
what gets posted. Also treats a missing/unapproved plan as DUE whenever a
slot's time has passed, so poller.py's own "cronograma ausente/nao
aprovado" GitHub Issue warning still fires as before -- this check must
never silently swallow that safety net.
"""
import datetime
import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANS_DIR = os.path.join(PROJECT_DIR, "content", "week_plans")

SCHEDULE = [
    {"slot": "feed", "weekdays": {1, 3}, "hour": 10, "minute": 0},
    {"slot": "story", "weekdays": {0, 1, 2, 3, 4}, "hour": 7, "minute": 0},
    {"slot": "reel", "weekdays": {0}, "hour": 9, "minute": 0},
]


def week_monday(date):
    return date - datetime.timedelta(days=date.weekday())


def load_plan(monday):
    path = os.path.join(PLANS_DIR, f"{monday.isoformat()}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def any_due(now):
    today_key = now.strftime("%Y-%m-%d")
    for entry in SCHEDULE:
        if now.weekday() not in entry["weekdays"]:
            continue
        scheduled = now.replace(hour=entry["hour"], minute=entry["minute"], second=0, microsecond=0)
        if now < scheduled:
            continue
        plan = load_plan(week_monday(now.date()))
        if plan is None or plan.get("status") != "approved":
            return True  # let poller.py's own run handle the warning/notify
        post = next(
            (p for p in plan.get("posts", []) if p.get("date") == today_key and p.get("slot") == entry["slot"]),
            None,
        )
        if post is not None and not post.get("posted"):
            return True
    return False


if __name__ == "__main__":
    due = any_due(datetime.datetime.now())
    print("DUE" if due else "NOT_DUE")
    sys.exit(0 if due else 1)
