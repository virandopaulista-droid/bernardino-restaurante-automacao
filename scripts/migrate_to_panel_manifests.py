#!/usr/bin/env python3
"""Converte os manifests proprios do Bernardino para o formato padrao do
painel BEEF MTK (content/bernardino_{stories,feed,reels}_manifest.json), para
o painel gerar/trocar/aprovar a semana como nos outros clientes (pedido do
Rob, 15/11/2026).

  stories <- brenda_stories_manifest.json + legacy/brenda_classificacao_2026-11-15.json
  feed    <- media_manifest.json   (folder relativo a "Imagens tratadas")
  reels   <- video_manifest.json   (folder relativo a "Videos Tratados" + drive_folder_id)

Uso: migrate_to_panel_manifests.py [--write] [--measure]
  --write    grava os 3 manifests (sem isso so mostra o relatorio)
  --measure  mede duracao e audio de cada reel ativo ainda sem medida e
             desativa os curtos (6s ou menos) ou mudos (-40 dB ou menos), as
             regras do Rob de 27/07 que o gerador antigo aplicava na hora de
             escolher (o painel nao roda ffprobe). Precisa do Drive montado
             (MEDIA_DIR_VIDEOS), entao roda no GitHub Actions
             (.github/workflows/migrate-manifests.yml).
Os manifests antigos NAO sao apagados.
"""
import collections
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORIES_FOLDER_ID = "12QI4iiRgecbxTZDcV-JllYHu6CBguG9c"
EXTRA_REEL_FOLDERS = {
    "Outubro 26": "1Q6ZiMrXOhpgt73VUwdXhJMMO8ISjepg4",
    "Dezembro 25/2": "1vXMyxfneyMbMID3VKnrdKroMdD-Dk-z2",
}
DISH_TAG = {"feijoada": "feijoada", "massas": "massas", "nhoque": "massas", "salmao": "salmao"}


def content(*parts):
    return os.path.join(ROOT, "content", *parts)


def load(name):
    with open(content(name), encoding="utf-8") as f:
        return json.load(f)


def norm(s):
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower().strip()


def rel_after(path, test):
    """Pastas (relativas) depois da ancora que satisfaz `test`, e o nome do arquivo."""
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    for i, p in enumerate(parts):
        if test(norm(p)):
            return [x.strip() for x in parts[i + 1:-1]], parts[-1]
    return None, parts[-1] if parts else ""


def stories():
    old = {a["file"]: a for a in load("brenda_stories_manifest.json")["assets"]}
    cls = {a["title"]: a for a in load(os.path.join("legacy", "brenda_classificacao_2026-11-15.json"))["artes"]}
    out = []
    for title, c in sorted(cls.items()):
        o = old.get(title, {})
        e = {
            "file": title,
            "type": "video" if title.lower().endswith((".mp4", ".mov")) else "image",
            "folder": "",
            "drive_folder_id": STORIES_FOLDER_ID,
            "source": "stories",
            "used": bool(o.get("used")),
            "used_at": o.get("used_at"),
            "description": c.get("headline", ""),
        }
        if c["category"] != "outro":
            e["category"] = c["category"]
        if c.get("weekday"):
            e["locked_weekday"] = c["weekday"]
        tag = DISH_TAG.get(norm(c.get("dish") or ""))
        if tag:
            e["dish_tags"] = [tag]
        reason = None
        if c["category"] == "outro":
            reason = "aviso/arte sem prato em destaque (" + (c.get("headline") or "")[:60] + ")"
        elif o.get("excluded") and "sem categoria" not in (o.get("exclude_reason") or ""):
            reason = o.get("exclude_reason")
        if reason:
            e["disabled"] = True
            e["disabled_reason"] = reason
        out.append(e)
    return {
        "_readme": "Pool de stories do Bernardino no padrao do painel (gerado por scripts/migrate_to_panel_manifests.py em 15/11/2026). Cada dia posta 1 de cada categoria (salgado, salada, doce), arte do dia (locked_weekday) primeiro.",
        "drive_folder_id": STORIES_FOLDER_ID,
        "assets": out,
    }


def feed():
    out, problems = [], []
    anchor = lambda n: "imagens" in n and "tratad" in n
    for x in load("media_manifest.json")["images"]:
        dirs, file = rel_after(x.get("converted_path") or x["source_path"], anchor)
        if dirs is None:
            dirs, file = rel_after(x["source_path"], anchor)
        e = {
            "file": file,
            "type": "image",
            "folder": "/".join(dirs or []),
            "category": x.get("category"),
            "used": bool(x.get("used")),
            "used_at": x.get("used_at"),
        }
        if x.get("description"):
            e["description"] = x["description"]
        if x.get("needs_review"):
            e["needs_review"] = True
        if x.get("excluded") or dirs is None or not (x.get("converted_path") or "").startswith("G:"):
            e["disabled"] = True
            e["disabled_reason"] = x.get("exclude_reason") or "caminho fora de 'Imagens tratadas'"
            if dirs is None:
                problems.append(x["source_path"])
        out.append(e)
    return {
        "_readme": "Pool de fotos do carrossel do Bernardino no padrao do painel (folder relativo a 'Imagens tratadas'). Gerado por scripts/migrate_to_panel_manifests.py em 15/11/2026.",
        "assets": out,
    }, problems


def reels():
    fmap = dict(load("videos_drive_folder_map.json")["folders"])
    fmap.update(EXTRA_REEL_FOLDERS)
    out, missing = [], collections.Counter()
    for x in load("video_manifest.json")["videos"]:
        dirs, file = rel_after(x["path"], lambda n: "video" in n and "tratad" in n)
        folder = "/".join(dirs or [])
        e = {
            "file": file,
            "type": "video",
            "folder": folder,
            "used": bool(x.get("used")),
            "used_at": x.get("used_at"),
            "duration_seconds": x.get("duration_seconds"),
            "audio_mean_db": x.get("audio_mean_db"),
        }
        # Video com o dia no nome ("Bernardino - terca.mp4", "...em uma sexta")
        # so pode sair nesse dia (o reel e na segunda).
        day = re.search(r"\b(segunda|terca|quarta|quinta|sexta|sabado|domingo)\b", norm(file))
        if day:
            e["locked_weekday"] = day.group(1)
        top = folder.split("/")[0]
        reason = None
        if top in ("Stories Reels", "Usados"):
            reason = f"pasta '{top}' fora da selecao de reel (igual ao gerador antigo)"
        elif x.get("too_short"):
            reason = "video curto demais (6s ou menos)"
        elif x.get("silent"):
            reason = "sem audio audivel"
        fid = fmap.get(folder)
        if fid:
            e["drive_folder_id"] = fid
        elif not reason:
            reason = f"sem drive_folder_id para a pasta '{folder}'"
            missing[folder] += 1
        if reason:
            e["disabled"] = True
            e["disabled_reason"] = reason
        out.append(e)
    # O video_manifest antigo tinha o MESMO video duas vezes (caminho G:\ e
    # /home/runner): junta numa entrada so (usado se qualquer copia foi;
    # desativado se qualquer copia foi -- todo motivo e do proprio arquivo).
    merged, idx = [], {}
    for e in out:
        k = (e["folder"], e["file"])
        b = idx.get(k)
        if b is None:
            idx[k] = e
            merged.append(e)
            continue
        b["used"] = b["used"] or e["used"]
        b["used_at"] = max(filter(None, [b.get("used_at"), e.get("used_at")]), default=None)
        for f in ("drive_folder_id", "locked_weekday", "duration_seconds", "audio_mean_db"):
            if b.get(f) is None and e.get(f) is not None:
                b[f] = e[f]
        if e.get("disabled") and not b.get("disabled"):
            b["disabled"], b["disabled_reason"] = True, e.get("disabled_reason")
    out = merged
    return {
        "_readme": "Pool de videos de reel do Bernardino no padrao do painel (folder relativo a 'Videos Tratados', drive_folder_id da subpasta publica). Gerado por scripts/migrate_to_panel_manifests.py em 15/11/2026.",
        "assets": out,
    }, missing


MIN_REEL_DURATION_SECONDS = 6
MIN_REEL_AUDIO_DB = -40


def measure_reels(rl):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from lib_media import get_audio_mean_volume_db, get_video_duration_seconds
    from poller import item_path
    for e in rl["assets"]:
        if e.get("disabled") or (e.get("duration_seconds") is not None and e.get("audio_mean_db") is not None):
            continue
        path = item_path(e, "reel")
        try:
            e["duration_seconds"] = get_video_duration_seconds(path)
            e["audio_mean_db"] = get_audio_mean_volume_db(path)
        except Exception as exc:
            e["disabled"] = True
            e["disabled_reason"] = f"nao consegui medir o video ({exc})"[:200]
            continue
        if e["duration_seconds"] <= MIN_REEL_DURATION_SECONDS:
            e["disabled"], e["disabled_reason"] = True, "video curto demais (6s ou menos)"
        elif e["audio_mean_db"] <= MIN_REEL_AUDIO_DB:
            e["disabled"], e["disabled_reason"] = True, "sem audio audivel"
        print(f"  medido {e['folder']}/{e['file']}: {e['duration_seconds']:.1f}s {e['audio_mean_db']:.0f}dB {'DESATIVADO' if e.get('disabled') else 'ok'}")


def report(name, m):
    a = m["assets"]
    live = [x for x in a if not x.get("disabled")]
    free = sum(1 for x in live if not x["used"])
    print(f"\n== {name}: {len(a)} itens, {len(live)} ativos, {len(a) - len(live)} desativados, {free} livres")
    return live


def main():
    write = "--write" in sys.argv
    st = stories()
    live = report("stories", st)
    c = collections.Counter((x.get("locked_weekday") or "generica", x.get("category")) for x in live)
    for d in ["segunda", "terca", "quarta", "quinta", "sexta", "generica"]:
        print(f"  {d:9}", {k: c.get((d, k), 0) for k in ("salgado", "salada", "doce")})
    fd, problems = feed()
    live = report("feed", fd)
    print("  livres por categoria:", dict(collections.Counter(x.get("category") for x in live if not x["used"])), "| sem pasta:", len(problems))
    rl, missing = reels()
    if "--measure" in sys.argv:
        measure_reels(rl)
    live = report("reels", rl)
    print("  ativos por pasta:", dict(collections.Counter(x["folder"] for x in live)), "| sem id:", dict(missing))
    if missing:
        raise RuntimeError("pasta de reel sem drive_folder_id")
    if write:
        for name, m in (("stories", st), ("feed", fd), ("reels", rl)):
            with open(content(f"bernardino_{name}_manifest.json"), "w", encoding="utf-8") as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
        print("\nGravado: content/bernardino_{stories,feed,reels}_manifest.json")
    else:
        print("\n(dry-run: nada gravado; rode com --write)")


if __name__ == "__main__":
    main()
