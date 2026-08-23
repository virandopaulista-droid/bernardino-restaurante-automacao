import os
import sys
import json
import subprocess
import urllib.request
import urllib.parse

TOKEN = os.environ["FB_PAGE_ACCESS_TOKEN"]
PAGE_ID = os.environ["FB_PAGE_ID"]


def call(path, params=""):
    url = f"https://graph.facebook.com/v21.0/{path}?{params}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


# Find the 2026-08-20 feed post by created_time prefix.
data = call(f"{PAGE_ID}/posts", "fields=message,created_time,attachments{media_type,subattachments{media{image{src}}}}&limit=15")
target = None
for p in data.get("data", []):
    if p.get("created_time", "").startswith("2026-08-20"):
        target = p
        break

if not target:
    print("NAO ACHEI o post de 2026-08-20 no feed do Facebook.", file=sys.stderr)
    sys.exit(1)

print("Post encontrado:", target["id"], target["created_time"])

urls = []
att = target.get("attachments", {}).get("data", [])
for a in att:
    subs = a.get("subattachments", {}).get("data", [])
    if subs:
        for s in subs:
            src = s.get("media", {}).get("image", {}).get("src")
            if src:
                urls.append(src)
    else:
        src = a.get("media", {}).get("image", {}).get("src")
        if src:
            urls.append(src)

print(f"{len(urls)} URLs de foto encontradas (fresh).")
if not urls:
    print("Sem URLs, abortando.", file=sys.stderr)
    sys.exit(1)

caption = """Sabor e variedade que fazem a diferença!
No Bernardino Restaurante, você encontra uma seleção incrível de pratos frescos e caseiros, preparados com todo o carinho.
Venha experimentar nossas opções que vão desde grelhados suculentos até deliciosas massas e acompanhamentos! 🍽️❤️

📍 Rua Bernardino de Campos, 201 — Brooklin/Campo Belo, SP
⏰ Segunda a sexta, 11h30 às 15h
👉 Venha almoçar com a gente!

#bernardinorestaurante #restauranteacampo #brooklinsp #campobelosp #almoçosp #comidacaseira #buffetporkilo #restaurantesp"""

caption_path = "/tmp/catchup_caption.txt" if os.name != "nt" else "catchup_caption.txt"
with open(caption_path, "w", encoding="utf-8") as f:
    f.write(caption)

cmd = ["bash", "scripts/post_instagram.sh", caption_path] + urls
print("Chamando:", cmd)
result = subprocess.run(cmd)
sys.exit(result.returncode)
