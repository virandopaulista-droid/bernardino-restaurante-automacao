#!/usr/bin/env python3
"""Free alternative to classify_media.py: classifies images into category
(prato_salgado / salada / doce / ambiente / outro) using a local CLIP model
(ViT-L/14) instead of the OpenAI vision API. No per-image cost after the
one-time model download (~1.7GB, cached in ~/.cache/huggingface).

Measured accuracy against 65 images previously labeled by OpenAI vision:
92.3% (60/65) — good enough for bulk classification. Confidence < 0.5 is
flagged as needs_review=true so low-confidence guesses get a human glance
before being trusted for a real post.

Does NOT write a "description" (no free local captioning here) — the actual
caption gets written later, at posting time, by looking at the one selected
photo with OpenAI vision (cheap: ~18 calls/week, not 1200).

Usage: classify_media_local.py [--limit=N]   (default: all remaining)
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clip_classifier import classify
from lib_media import append_image_entry, iter_image_files, load_manifest, resolve_classifiable_path

LIMIT = None
for arg in sys.argv[1:]:
    if arg.startswith("--limit="):
        LIMIT = int(arg.split("=", 1)[1])

CONFIDENCE_THRESHOLD = 0.5


def main():
    manifest = load_manifest()
    already = {entry["source_path"] for entry in manifest["images"]}

    candidates = [p for p in iter_image_files() if str(p) not in already]
    print(f"Total de imagens candidatas ainda nao classificadas: {len(candidates)}")

    todo = candidates[:LIMIT] if LIMIT else candidates
    print(f"Processando {len(todo)} nesta execucao (CLIP local, sem custo por chamada)...")

    done = 0
    counts = {}
    review_count = 0
    for src_path in todo:
        try:
            classifiable_path = resolve_classifiable_path(src_path)
            category, confidence = classify(classifiable_path)
        except Exception as e:
            print(f"ERRO ao processar {src_path}: {e}", file=sys.stderr)
            continue

        needs_review = confidence < CONFIDENCE_THRESHOLD
        entry = {
            "source_path": str(src_path),
            "converted_path": str(classifiable_path),
            "category": category,
            "confidence": confidence,
            "needs_review": needs_review,
            "description": "",
            "classified_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "method": "clip-vit-large-patch14",
            "used": False,
            "used_at": None,
        }
        append_image_entry(entry)  # reloads fresh each time, won't clobber concurrent 'used' updates

        counts[category] = counts.get(category, 0) + 1
        if needs_review:
            review_count += 1
        done += 1
        flag = " [REVISAR]" if needs_review else ""
        print(f"[{done}/{len(todo)}] {src_path.name} -> {category} ({confidence}){flag}")

    print("\nResumo desta execucao:")
    for cat, n in counts.items():
        print(f"  {cat}: {n}")
    print(f"  precisando revisao (confianca < {CONFIDENCE_THRESHOLD}): {review_count}")
    remaining = len(candidates) - done
    print(f"Restam {remaining} imagens nao classificadas.")


if __name__ == "__main__":
    main()
