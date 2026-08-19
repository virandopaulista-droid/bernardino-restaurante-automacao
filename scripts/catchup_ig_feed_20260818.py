#!/usr/bin/env python3
"""TEMP one-off: republica so a perna do Instagram do feed de 2026-08-18,
que falhou com erro transitorio da Meta (ja corrigido pra proximas vezes).
Busca as URLs de imagem ATUAIS do post do Facebook ja publicado (evita
depender das URLs antigas do log, que podem ter expirado), escreve a
legenda, e chama post_instagram.sh direto. Sera removido apos rodar."""
import json
import os
import subprocess
import sys
import urllib.request

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
token = os.environ["FB_PAGE_ACCESS_TOKEN"]
page_id = os.environ["FB_PAGE_ID"]
post_id = f"{page_id}_1693325106126727"

CAPTION = """Sabor em cada detalhe!
Nossos grelhados suculentos e as deliciosas porções de salgados são apenas o começo.
Venha se deliciar com uma variedade incrível de saladas frescas e sobremesas irresistíveis! 🍽️❤️

📍 Rua Bernardino de Campos, 201 — Brooklin/Campo Belo, SP
⏰ Segunda a sexta, 11h30 às 15h
👉 Venha almoçar com a gente!

#bernardinorestaurante #restauranteacampo #brooklinsp #campobelosp #almoçosp #comidacaseira #buffetporkilo #restaurantesp"""


def get_json(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


data = get_json(f"https://graph.facebook.com/v20.0/{post_id}?fields=attachments")
urls = []
for att in data.get("attachments", {}).get("data", []):
    subs = att.get("subattachments", {}).get("data", [])
    items = subs if subs else [att]
    for it in items:
        img = it.get("media", {}).get("image", {})
        if img.get("src"):
            urls.append(img["src"])

print(f"URLs atuais encontradas: {len(urls)}", file=sys.stderr)
if len(urls) != 5:
    print(f"ERRO: esperava 5 imagens, achei {len(urls)}. Abortando.", file=sys.stderr)
    raise SystemExit(1)

caption_path = os.path.join(PROJECT_DIR, "content", "caption_catchup_20260818.txt")
with open(caption_path, "w", encoding="utf-8") as f:
    f.write(CAPTION)

# post_instagram.sh faz `source .env` -- nesse ponto do pipeline (antes do
# mount) esse arquivo ainda nao existe, entao escreve so o minimo que o
# script precisa.
env_path = os.path.join(PROJECT_DIR, ".env")
ig_business_id = os.environ["IG_BUSINESS_ID"]
with open(env_path, "w", encoding="utf-8") as f:
    f.write(f'FB_PAGE_ACCESS_TOKEN="{token}"\n')
    f.write(f'IG_BUSINESS_ID="{ig_business_id}"\n')

result = subprocess.run(
    ["bash", os.path.join(PROJECT_DIR, "scripts", "post_instagram.sh"), caption_path, *urls],
    text=True,
)
raise SystemExit(result.returncode)
