#!/usr/bin/env python3
"""Escreve com IA (olhando a midia real) a legenda dos posts de feed e reel
que o painel BEEF MTK gerou com `caption_pending_ai: true` -- o painel nao
roda OpenAI, entao gera a semana com legenda provisoria e este script (via
.github/workflows/fill-captions.yml) troca pela legenda de verdade antes do
Rob aprovar. Mesmos scripts de sempre: caption_from_photo.py (carrossel) e
caption_for_reel.py (reel), que seguem docs/guia-bernardino.md.

Duas fases, pra nao atropelar uma edicao feita no painel enquanto a IA
trabalhava:
  fill_ai_captions.py compute <saida.json>   gera as legendas (lento, usa o Drive)
  fill_ai_captions.py apply <saida.json>     grava no plano mais recente do repo
No apply, so entra a legenda de post que AINDA esta pendente e com os MESMOS
arquivos de quando a legenda foi escrita (se o Rob trocou a foto, a legenda
velha nao serve e fica pra proxima rodada).
"""
import datetime
import glob
import json
import os
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPTS_DIR)
PLANS_DIR = os.path.join(PROJECT_DIR, "content", "week_plans")
sys.path.insert(0, SCRIPTS_DIR)
from poller import item_path  # noqa: E402  (mesma resolucao de caminho da postagem)


def key(plan_file, post):
    files = "|".join(it.get("file") or it.get("path", "") for it in post["items"])
    return f"{os.path.basename(plan_file)}::{post['date']}::{post['slot']}::{files}"


def pending_posts():
    # So posts de AMANHA em diante: o de hoje ja pode estar sendo publicado
    # pelo poller, e gravar a legenda nele agora so cria conflito no mesmo
    # trecho do plano (achado na revisao de 15/11). O de hoje sai com a
    # legenda provisoria, com aviso no log do poller.
    today = datetime.date.today().isoformat()
    for plan_file in sorted(glob.glob(os.path.join(PLANS_DIR, "*.json"))):
        with open(plan_file, encoding="utf-8") as f:
            plan = json.load(f)
        for post in plan.get("posts", []):
            if (post.get("caption_pending_ai") and not post.get("posted") and post["slot"] in ("feed", "reel")
                    and post["date"] > today):
                yield plan_file, post


def compute(out_path):
    result = {}
    for plan_file, post in pending_posts():
        kind = post["slot"]
        paths = [item_path(it, kind) for it in post["items"]]
        try:
            # Sem o arquivo a IA "escreve" sem ver a midia (caption_for_reel.py
            # nao falha quando nao consegue tirar quadros) -- e inventa prato.
            missing = [p for p in paths if not os.path.exists(p)]
            if missing:
                raise RuntimeError(f"arquivo nao encontrado no Drive: {missing}")
            if kind == "feed":
                cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "caption_from_photo.py"), "feed", *paths]
            else:
                cmd = [sys.executable, os.path.join(SCRIPTS_DIR, "caption_for_reel.py"), paths[0]]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip()[-500:])
            with open(r.stdout.strip().splitlines()[-1], encoding="utf-8") as f:
                caption = f.read().strip()
            if not caption:
                raise RuntimeError("legenda vazia")
            result[key(plan_file, post)] = caption
            print(f"OK {post['date']} {kind}: {caption[:80]!r}")
        except Exception as e:  # uma falha nao derruba as outras legendas
            print(f"ERRO {post['date']} {kind}: {e}", file=sys.stderr)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"{len(result)} legenda(s) escrita(s)")


def apply(in_path):
    with open(in_path, encoding="utf-8") as f:
        captions = json.load(f)
    changed_files = set()
    plans = {}
    for plan_file, post in pending_posts():
        cap = captions.get(key(plan_file, post))
        if not cap:
            continue
        plans.setdefault(plan_file, None)
    for plan_file in plans:
        with open(plan_file, encoding="utf-8") as f:
            plan = json.load(f)
        for post in plan.get("posts", []):
            cap = captions.get(key(plan_file, post))
            if cap and post.get("caption_pending_ai") and not post.get("posted"):
                post["caption_text"] = cap
                post.pop("caption_pending_ai", None)
                changed_files.add(plan_file)
        if plan_file in changed_files:
            with open(plan_file, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"legendas aplicadas em {len(changed_files)} plano(s)")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("compute", "apply"):
        print(__doc__)
        raise SystemExit(2)
    (compute if sys.argv[1] == "compute" else apply)(sys.argv[2])
