#!/usr/bin/env python3
"""Writes a Reel caption based on what's ACTUALLY visible in the video --
extracts a few frames and uses vision, same principle as caption_from_photo.py
(never invent a dish that isn't shown). Replaces the earlier blind version
that picked a random menu highlight with no idea what the video showed (bug
found 2026-07-27: captioned a video literally named "Salada.mp4" as being
about grelhados, because it never looked at the video at all).

Usage: caption_for_reel.py <video_path>
Prints the caption file path.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_media import FIXED_CAPTION_FOOTER, FIXED_HASHTAGS

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_DIR, "docs", "guia-bernardino.md")

video_path = sys.argv[1]

with open(GUIDE_PATH, "r", encoding="utf-8") as f:
    guide_text = f.read()


def extract_frames(path, n=3):
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, check=True,
            )
            duration = float(probe.stdout.strip())
        except Exception:
            duration = 6.0
        for i in range(n):
            ts = duration * (i + 1) / (n + 1)
            frame_path = os.path.join(tmp, f"frame{i}.jpg")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", path, "-frames:v", "1", frame_path, "-loglevel", "error"],
                check=False,
            )
            if os.path.exists(frame_path):
                with open(frame_path, "rb") as f:
                    frames.append(base64.b64encode(f.read()).decode("ascii"))
    return frames


frames_b64 = extract_frames(video_path)
image_content = [
    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}}
    for b64 in frames_b64
]

system_prompt = (
    "Voce e o redator de conteudo do Facebook/Instagram do \"Bernardino Restaurante\", "
    "um restaurante self-service a quilo REAL. Voce recebeu alguns frames extraidos de um "
    "REEL real (video de bastidores/buffet/cliente). Olhe com atencao e escreva a legenda "
    "descrevendo APENAS o que voce realmente ve nos frames — NUNCA invente pratos, "
    "ingredientes ou cenas que nao aparecem (ex: nao fale de grelhados se o video mostra "
    "saladas). Se os frames nao deixarem claro um prato especifico, fale de forma mais geral "
    "sobre o ambiente/experiencia, sem inventar detalhes.\n\n"
    f"{guide_text}\n\n"
    'Responda SOMENTE com JSON: {"caption": "texto com quebras de linha reais entre headline/'
    'desenvolvimento/CTA"}\n'
    "NAO inclua hashtags — elas sao inseridas automaticamente pelo script, sempre por ultimo.\n"
    "IMPORTANTE: o CTA final da SUA legenda NAO pode ser a frase '👉 Venha almoçar com a gente!' "
    "nem nada muito parecido — essa frase exata ja aparece no rodape fixo (inserido logo apos a "
    "sua legenda, automaticamente). Escreva um CTA diferente, ou termine sem CTA generico.\n"
    "Respeite sempre o horario de funcionamento (seg-sex 11h30-15h) — nunca mencione fim de "
    "semana, delivery ou jantar/noite."
)

payload = json.dumps({
    "model": "gpt-4o-mini",
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [{"type": "text", "text": "Escreva a legenda pra esse reel."}] + image_content},
    ],
    "response_format": {"type": "json_object"},
    "temperature": 0.9,
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.openai.com/v1/chat/completions",
    data=payload,
    headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
except urllib.error.HTTPError as e:
    print(f"Erro da API OpenAI: {e.read().decode('utf-8')}", file=sys.stderr)
    raise SystemExit(1)

caption = json.loads(body["choices"][0]["message"]["content"])["caption"].strip()
caption = f"{caption}\n\n{FIXED_CAPTION_FOOTER}\n\n{FIXED_HASHTAGS}"

fd, path = tempfile.mkstemp(prefix="caption_reel_", suffix=".txt", dir=os.path.join(PROJECT_DIR, "content"))
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write(caption)
print(path)
