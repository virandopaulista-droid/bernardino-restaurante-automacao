#!/usr/bin/env python3
"""Scans the Bernardino Restaurante Drive media folders for images not yet
in the manifest, converts HEIC to JPEG, and classifies each one via OpenAI
vision into a category (prato_salgado / salada / doce / ambiente / outro)
plus a short factual description. Results are appended to
content/media_manifest.json incrementally (safe to interrupt and rerun).

Usage: classify_media.py [--limit=N]   (default limit: 40 new images/run)
"""
import base64
import datetime
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_media import CATEGORIES, append_image_entry, iter_image_files, load_manifest, resolve_classifiable_path

LIMIT = 40
for arg in sys.argv[1:]:
    if arg.startswith("--limit="):
        LIMIT = int(arg.split("=", 1)[1])

CATEGORY_LIST = ", ".join(CATEGORIES)

SYSTEM_PROMPT = (
    "Voce esta classificando fotos reais do restaurante \"Bernardino Restaurante\" "
    "(self-service a quilo, culinaria brasileira) para uso em posts/stories. "
    "Olhe a imagem e responda SOMENTE com um JSON valido, sem markdown, no formato:\n"
    '{"category": "uma das opcoes: ' + CATEGORY_LIST + '", '
    '"description": "1 frase curta em portugues descrevendo o que aparece na foto"}\n\n'
    "Guia das categorias:\n"
    "- prato_salgado: prato quente, grelhado, comida salgada montada no prato ou no buffet\n"
    "- salada: saladas, folhas, pista fria\n"
    "- doce: sobremesas, doces, frutas de sobremesa\n"
    "- ambiente: salao, mesas, fachada, decoracao, sem foco em comida\n"
    "- outro: qualquer coisa que nao se encaixe acima (pessoas, logo, foto ilegivel, etc.)"
)


def classify_image(path):
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Classifique essa foto."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "low"}},
                ],
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
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
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())

    content = json.loads(body["choices"][0]["message"]["content"])
    category = content.get("category", "outro")
    if category not in CATEGORIES:
        category = "outro"
    return category, content.get("description", "")


def main():
    manifest = load_manifest()
    already = {entry["source_path"] for entry in manifest["images"]}

    candidates = [p for p in iter_image_files() if str(p) not in already]
    print(f"Total de imagens candidatas ainda nao classificadas: {len(candidates)}")

    todo = candidates[:LIMIT]
    print(f"Processando {len(todo)} nesta execucao (limite {LIMIT})...")

    done = 0
    counts = {}
    for src_path in todo:
        try:
            classifiable_path = resolve_classifiable_path(src_path)
            category, description = classify_image(classifiable_path)
        except urllib.error.HTTPError as e:
            print(f"ERRO na API OpenAI para {src_path}: {e.read().decode('utf-8')}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"ERRO ao processar {src_path}: {e}", file=sys.stderr)
            continue

        entry = {
            "source_path": str(src_path),
            "converted_path": str(classifiable_path),
            "category": category,
            "description": description,
            "classified_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "used": False,
            "used_at": None,
        }
        append_image_entry(entry)  # reloads fresh each time, won't clobber concurrent 'used' updates

        counts[category] = counts.get(category, 0) + 1
        done += 1
        print(f"[{done}/{len(todo)}] {src_path.name} -> {category} ({description})")

    print("\nResumo desta execucao:")
    for cat in CATEGORIES:
        print(f"  {cat}: {counts.get(cat, 0)}")
    remaining = len(candidates) - done
    print(f"Restam {remaining} imagens nao classificadas (rode de novo pra continuar).")


if __name__ == "__main__":
    main()
