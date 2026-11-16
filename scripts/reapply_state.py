#!/usr/bin/env python3
"""Reaplica o estado do poller (posted/posted_at/posting_error, por post e por
item) em cima da versao MAIS RECENTE do repositorio, quando o `git rebase`
do commit de estado da conflito.

Por que existe (achado na revisao de 15/11/2026): o fallback antigo do
poller.yml fazia `rebase --abort; reset --soft origin/master` e nao criava
commit nenhum -- o `git push` seguinte respondia "Everything up-to-date", o
passo dizia "push ok" e as marcas de publicado sumiam sem aviso (risco real de
post duplicado). Com o painel e o fill-captions.yml tambem gravando nos
planos, esse conflito ficou mais provavel.

Uso: reapply_state.py <pasta com a NOSSA versao dos arquivos de content/>
     (o repositorio ja deve estar em origin/master)
- week_plans/*.json: parte da versao remota e copia so os campos de estado
  dos posts (casados por data + slot) e dos itens (por posicao, se o arquivo
  for o mesmo). Nunca desmarca um post publicado.
- outros arquivos de content/: fica a nossa versao (comportamento antigo).
"""
import json
import os
import shutil
import sys

STATE = ("posted", "posted_at", "posting_error")


def name_of(it):
    return it.get("file") or os.path.basename((it.get("path") or "").replace("\\", "/"))


def merge_plan(ours_path, repo_path):
    with open(ours_path, encoding="utf-8") as f:
        ours = json.load(f)
    if not os.path.exists(repo_path):
        shutil.copyfile(ours_path, repo_path)
        return
    with open(repo_path, encoding="utf-8") as f:
        theirs = json.load(f)
    by_key = {(p["date"], p["slot"]): p for p in theirs.get("posts", [])}
    for p in ours.get("posts", []):
        t = by_key.get((p["date"], p["slot"]))
        if t is None:
            continue
        for k in STATE:
            if k in p and not (k == "posted" and t.get("posted") and not p.get("posted")):
                t[k] = p[k]
        for i, it in enumerate(p.get("items", [])):
            if i < len(t.get("items", [])) and name_of(t["items"][i]) == name_of(it):
                for k in ("posted", "posted_at"):
                    if k in it:
                        t["items"][i][k] = it[k]
    with open(repo_path, "w", encoding="utf-8") as f:
        json.dump(theirs, f, ensure_ascii=False, indent=2)


def main():
    ours_dir = sys.argv[1]
    for root, _dirs, files in os.walk(ours_dir):
        for name in files:
            ours_path = os.path.join(root, name)
            rel = os.path.relpath(ours_path, ours_dir)
            repo_path = os.path.join(os.getcwd(), rel)
            os.makedirs(os.path.dirname(repo_path), exist_ok=True)
            if rel.replace("\\", "/").startswith("content/week_plans/") and name.endswith(".json"):
                merge_plan(ours_path, repo_path)
            else:
                shutil.copyfile(ours_path, repo_path)
            print(f"reaplicado: {rel}")


if __name__ == "__main__":
    main()
