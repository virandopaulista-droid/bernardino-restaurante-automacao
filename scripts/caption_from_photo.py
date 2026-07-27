#!/usr/bin/env python3
"""Looks at a real Bernardino Restaurante photo (or a list of photos, for a
carousel) and writes a caption following docs/guia-bernardino.md — describing
only what's genuinely visible, never inventing dishes/details. Cheap: one
vision call per photo, only run at actual posting time (not for bulk
classification, that's classify_media.py / classify_media_local.py).

Usage: caption_from_photo.py <format> <image_path> [image_path2 ...]
  format: feed | story | reel
Writes the caption to a temp file under content/ and prints its path.
"""
import base64
import json
import mimetypes
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_media import FIXED_CAPTION_FOOTER, FIXED_HASHTAGS

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_DIR, "docs", "guia-bernardino.md")

post_format = sys.argv[1]
image_paths = sys.argv[2:]
if not image_paths:
    print("Forneca ao menos 1 caminho de imagem.", file=sys.stderr)
    raise SystemExit(1)

with open(GUIDE_PATH, "r", encoding="utf-8") as f:
    guide_text = f.read()

image_content = []
for path in image_paths:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    image_content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "low"}})

format_instructions = {
    "feed": "Este e um POST DE CARROSSEL (5 fotos) para Facebook e Instagram — a legenda e UMA SO, cobrindo o conjunto das fotos, nao uma por foto. Estrutura: headline chamativa (linha propria), 1-2 linhas de desenvolvimento, CTA claro (linha propria), seguindo o formato do guia.",
    "story": "Este e um STORY (parte de uma sequencia de 3: prato salgado, salada, doce). Escreva um texto BEM CURTO (1 frase ou poucas palavras, estilo overlay de story), sem CTA longo, sem hashtags.",
    "reel": "Este e um REEL. Escreva uma legenda curta e envolvente pra acompanhar o video, seguindo o tom do guia, com CTA.",
}.get(post_format, "Escreva a legenda seguindo o guia.")

system_prompt = (
    "Voce e o redator de conteudo do Facebook/Instagram do \"Bernardino Restaurante\", "
    "um restaurante self-service a quilo REAL (nao e conteudo de receita/IA). "
    "As fotos fornecidas sao REAIS, ja tratadas pelo cliente. Olhe com atencao e descreva "
    "APENAS o que voce realmente ve — nunca invente pratos, precos ou detalhes que nao aparecem. "
    f"{format_instructions}\n\n"
    f"{guide_text}\n\n"
    "Responda SOMENTE com um JSON valido, sem markdown, no formato:\n"
    '{"caption": "texto completo em portugues"}\n'
    "IMPORTANTE: NAO inclua hashtags na legenda — elas sao inseridas automaticamente pelo script, "
    "sempre por ultimo. Escreva so headline + desenvolvimento + CTA.\n"
    "IMPORTANTE: o guia acima mostra, como exemplo, o texto exato do rodape fixo (endereco, "
    "horario, 'Venha almoçar com a gente!') — isso e so pra sua referencia de que ele existe. "
    "NAO copie esse bloco nem nenhuma linha parecida (endereco/horario/CTA generico) pra dentro "
    "da SUA legenda — ele e inserido automaticamente pelo script logo depois, e copia-lo cria "
    "duplicacao. Sua legenda deve conter SO headline + desenvolvimento + CTA proprio, nada do "
    "rodape.\n"
    "IMPORTANTE - formatacao: use quebras de linha reais (\\n) separando CADA parte da legenda "
    "(headline e cada linha de desenvolvimento e CTA) — NUNCA escreva tudo em um unico "
    "paragrafo corrido. Emojis podem ficar na mesma linha do texto que acompanham.\n"
    "IMPORTANTE: respeite SEMPRE o horario de funcionamento (seg-sex, 11h30-15h) — nunca mencione "
    "fim de semana, delivery ou jantar/noite."
)

payload = json.dumps({
    "model": "gpt-4o-mini",
    "messages": [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [{"type": "text", "text": "Escreva a legenda pra essa(s) foto(s)."}] + image_content,
        },
    ],
    "response_format": {"type": "json_object"},
    "temperature": 0.9,
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.openai.com/v1/chat/completions",
    data=payload,
    headers={
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"Erro da API OpenAI (vision): {e.read().decode('utf-8')}", file=sys.stderr)
    raise SystemExit(1)

content = json.loads(body["choices"][0]["message"]["content"])
caption = content["caption"].strip()

if post_format in ("feed", "reel"):
    caption = f"{caption}\n\n{FIXED_CAPTION_FOOTER}"
    if post_format == "feed":
        caption = f"{caption}\n\n{FIXED_HASHTAGS}"

caption_fd, caption_path = tempfile.mkstemp(prefix="caption_", suffix=".txt", dir=os.path.join(PROJECT_DIR, "content"))
with os.fdopen(caption_fd, "w", encoding="utf-8") as f:
    f.write(caption)

print(caption_path)
