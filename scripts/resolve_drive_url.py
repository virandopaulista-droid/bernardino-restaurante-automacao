#!/usr/bin/env python3
"""Resolves a filename inside a publicly-shared Drive folder to a public
direct-download URL, without needing Drive API credentials. Same technique
proven working for Bernardino/TopTop's automations.

How it works: the folder's public embed view (embeddedfolderview) exposes
each file as an <a href="https://drive.google.com/file/d/<ID>/view..."> --
we scrape that HTML for filename->file_id, then build the direct-download
link (https://drive.google.com/uc?export=download&id=<ID>).

Usage: resolve_drive_url.py <filename> <folder_id>
  GM's reels pool spans several month subfolders, so folder_id is always
  required here (no single default folder like Bernardino/TopTop have).
Prints the direct-download URL, or exits 1 with an error if not found.
"""
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

PATTERN = re.compile(
    r'href="https://drive\.google\.com/file/d/([a-zA-Z0-9_-]+)/view[^"]*"[^>]*>.*?'
    r'flip-entry-title">([^<]+)</div>'
)


def reshare_folder(folder_id):
    """Confirmado 2026-08-19 (Au Gratin): o 401 nao era passageiro -- o
    compartilhamento publico ("qualquer pessoa com o link") da pasta tinha
    caido de verdade (rclone com acesso autenticado via OAuth continuava
    enxergando os arquivos normalmente, so o embed anonimo que quebrou).
    `rclone link` reestabelece esse compartilhamento se ele nao existir
    mais -- best-effort, nunca derruba o processo se falhar."""
    try:
        subprocess.run(
            ["rclone", "link", "gdrive:", "--drive-root-folder-id", folder_id],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as e:
        print(f"AVISO: rclone link falhou (nao critico): {e}", file=sys.stderr)


def fetch_id_map(folder_id, attempts=4, delay_seconds=8):
    embed_url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"
    req = urllib.request.Request(embed_url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            id_map = {name: file_id for file_id, name in PATTERN.findall(html)}
            # Confirmado real 2026-08-28 (Au Gratin, reel): um 401 na 1a
            # tentativa aciona o reshare_folder() acima, e a tentativa
            # seguinte volta com HTTP 200 mas 0 arquivos -- o
            # compartilhamento tinha acabado de ser restabelecido e o
            # embed anonimo ainda nao tinha propagado o conteudo. Um
            # dicionario vazio aqui NAO e confiavel como "pasta realmente
            # vazia" logo depois de um reshare -- trata como retry-avel
            # tambem (mesmo esperando entre tentativas), em vez de devolver
            # {} direto pro chamador reportar "nao encontrado" sem nunca
            # ter visto o conteudo de verdade.
            if id_map or attempt == attempts:
                return id_map
            print(f"AVISO: pasta retornou 0 arquivos (tentativa {attempt}/{attempts}), pode ser propagacao do reshare -- tentando de novo em {delay_seconds}s...", file=sys.stderr)
            time.sleep(delay_seconds)
        except urllib.error.HTTPError as e:
            if attempt == attempts:
                raise
            if e.code == 401:
                print(f"AVISO: HTTP 401 buscando a pasta do Drive (tentativa {attempt}/{attempts}) -- reestabelecendo compartilhamento publico...", file=sys.stderr)
                reshare_folder(folder_id)
            else:
                print(f"AVISO: erro HTTP {e.code} buscando a pasta do Drive (tentativa {attempt}/{attempts}), tentando de novo em {delay_seconds}s...", file=sys.stderr)
                time.sleep(delay_seconds)
    return {}


def main():
    if len(sys.argv) != 3:
        print("Uso: resolve_drive_url.py <filename> <folder_id>", file=sys.stderr)
        raise SystemExit(1)
    filename = sys.argv[1]
    folder_id = sys.argv[2]
    id_map = fetch_id_map(folder_id)
    file_id = id_map.get(filename)
    if not file_id:
        print(f"ERRO: '{filename}' nao encontrado no embed da pasta ({len(id_map)} arquivos vistos).", file=sys.stderr)
        raise SystemExit(1)
    print(f"https://drive.google.com/uc?export=download&id={file_id}")


if __name__ == "__main__":
    main()
