#!/usr/bin/env python3
"""Marks a week plan as approved -- the poller refuses to post anything from
a plan that isn't approved (see poller.py). Only call this after the user
has actually reviewed and approved the week's gallery.

Usage: approve_week_plan.py <plan_json_path>
"""
import json
import sys

plan_path = sys.argv[1]
with open(plan_path, encoding="utf-8") as f:
    plan = json.load(f)

plan["status"] = "approved"
with open(plan_path, "w", encoding="utf-8") as f:
    json.dump(plan, f, ensure_ascii=False, indent=2)

print(f"Plano {plan['week_start']} aprovado.")
