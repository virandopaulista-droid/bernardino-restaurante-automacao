#!/usr/bin/env python3
"""Builds a standalone HTML gallery from a week plan (content/week_plans/*.json)
for human approval -- embeds every image/video-thumbnail (downscaled) and two
fonts as base64, so the file works offline with no external dependencies.

Usage: build_week_gallery.py <plan_json_path>
Writes <plan_json_path without .json>_gallery.html next to the plan.
Prints the gallery HTML path.
"""
import base64
import datetime
import html
import io
import json
import os
import subprocess
import sys
import tempfile
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.environ.get("GALLERY_FONTS_DIR", os.path.join(PROJECT_DIR, "assets", "fonts"))

WEEKDAY_LABELS = {
    "segunda": "Segunda-feira", "terca": "Terça-feira", "quarta": "Quarta-feira",
    "quinta": "Quinta-feira", "sexta": "Sexta-feira",
}
SLOT_LABELS = {"feed": "Feed", "story": "Stories", "reel": "Reel"}
SLOT_SUBLABEL = {
    "feed": "Facebook + Instagram, carrossel",
    "story": "Facebook + Instagram, 3 stories",
    "reel": "Facebook + Instagram, vídeo",
}
CATEGORY_LABELS = {"salgado": "Prato salgado", "salada": "Salada", "doce": "Doce"}
MONTH_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
            "agosto", "setembro", "outubro", "novembro", "dezembro"]


def fmt_date_long(iso_date):
    d = datetime.date.fromisoformat(iso_date)
    return f"{d.day} de {MONTH_PT[d.month - 1]}"


def to_data_uri_image(path, max_width=480):
    # Downscale before embedding -- the real client photos are ~20MB camera
    # originals; embedding those raw would balloon the gallery to hundreds of
    # MB (confirmed: a first attempt hit 275MB and was unusable). A resized
    # JPEG is more than enough resolution to approve a thumbnail choice.
    from PIL import Image

    # The Drive mount (rclone, minimal VFS cache) 404s a file that genuinely
    # exists when it's the first file touched in a given subfolder this run
    # -- listing the parent dir first forces rclone to refresh its cache.
    for attempt in range(1, 7):
        try:
            os.listdir(os.path.dirname(path))
        except OSError:
            pass
        try:
            img = Image.open(path)
            break
        except FileNotFoundError:
            if attempt == 6:
                raise
            time.sleep(10)
    img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=78)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def to_data_uri_video(path):
    # Re-encode at review quality instead of embedding the original -- a
    # single 15MB source video (typical for the real client's Reels) would
    # blow up the gallery just like the unresized photos did. 480px/CRF30 is
    # plenty to judge "is this the right clip", not meant for final posting.
    with tempfile.TemporaryDirectory() as tmp:
        out_path = os.path.join(tmp, "preview.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-vf", "scale=480:-2", "-c:v", "libx264",
             "-crf", "30", "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k",
             out_path, "-loglevel", "error"],
            check=False,
        )
        src_path = out_path if os.path.exists(out_path) else path
        with open(src_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:video/mp4;base64,{b64}"


def to_data_uri_video_thumb(path):
    with tempfile.TemporaryDirectory() as tmp:
        frame_path = os.path.join(tmp, "frame.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "1.0", "-i", path, "-frames:v", "1", "-vf", "scale=480:-1", frame_path, "-loglevel", "error"],
            check=False,
        )
        if not os.path.exists(frame_path):
            return None
        with open(frame_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"


def load_font_b64(name):
    path = os.path.join(FONTS_DIR, f"{name}.b64")
    if os.path.exists(path):
        with open(path, encoding="ascii") as f:
            return f.read()
    ttf_path = os.path.join(FONTS_DIR, f"{name}.ttf")
    with open(ttf_path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def render_item(item):
    path = item["path"]
    fname = html.escape(os.path.basename(path))
    cat = item.get("category")
    cat_class = f" cat-{cat}" if cat else ""
    if item["type"] == "video":
        poster = to_data_uri_video_thumb(path)
        poster_attr = f' poster="{poster}"' if poster else ""
        media_html = (
            f'<video class="thumb-media" controls preload="metadata"{poster_attr}>'
            f'<source src="{to_data_uri_video(path)}" type="video/mp4">'
            f'</video>'
        )
        item_class = "item item-video"
    else:
        media_html = f'<img class="thumb-media" src="{to_data_uri_image(path)}" alt="{fname}" loading="lazy">'
        item_class = "item"
    cat_tag = f'<span class="cat-tag{cat_class}">{CATEGORY_LABELS.get(cat, cat)}</span>' if cat else ""
    return f'''<figure class="{item_class}">
      <div class="thumb">{media_html}</div>
      {cat_tag}
    </figure>'''


def render_caption(caption_file):
    if not caption_file or not os.path.exists(caption_file):
        return ""
    with open(caption_file, encoding="utf-8") as f:
        text = f.read()
    return f'<pre class="ticket">{html.escape(text)}</pre>'


def render_slot(post):
    slot = post["slot"]
    items_html = "".join(render_item(it) for it in post["items"])
    caption_html = render_caption(post.get("caption_file"))
    return f'''
    <div class="slot slot-{slot}">
      <div class="slot-head">
        <span class="slot-name">{SLOT_LABELS[slot]}</span>
        <span class="slot-sub">{SLOT_SUBLABEL[slot]}</span>
      </div>
      <div class="filmstrip">{items_html}</div>
      {caption_html}
    </div>'''


def render_day(date_iso, posts):
    weekday = WEEKDAY_LABELS.get(posts[0]["weekday"], posts[0]["weekday"])
    slots_html = "".join(render_slot(p) for p in sorted(posts, key=lambda p: {"story": 0, "reel": 1, "feed": 2}[p["slot"]]))
    return f'''
    <section class="day" id="day-{date_iso}">
      <div class="day-head">
        <span class="weekday">{weekday}</span>
        <span class="date">{fmt_date_long(date_iso)}</span>
      </div>
      {slots_html}
    </section>'''


def main():
    plan_path = sys.argv[1]
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)

    by_date = {}
    for post in plan["posts"]:
        by_date.setdefault(post["date"], []).append(post)

    days_html = "".join(render_day(d, posts) for d, posts in sorted(by_date.items()))

    fraunces_b64 = load_font_b64("Fraunces")
    work_sans_b64 = load_font_b64("WorkSans")

    week_end = (datetime.date.fromisoformat(plan["week_start"]) + datetime.timedelta(days=4)).isoformat()
    status = plan["status"]
    status_label = "aguardando aprovação" if status == "pending_approval" else "aprovado"

    html_doc = f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cronograma — semana de {fmt_date_long(plan["week_start"])}</title>
<style>
@font-face {{
  font-family: "Fraunces"; font-weight: 300 700; font-style: normal;
  src: url(data:font/ttf;base64,{fraunces_b64}) format("truetype-variations");
}}
@font-face {{
  font-family: "Work Sans"; font-weight: 300 700; font-style: normal;
  src: url(data:font/ttf;base64,{work_sans_b64}) format("truetype-variations");
}}

:root {{
  --bg: #efe6d3;
  --surface: #fffdf8;
  --surface-alt: #fbf1de;
  --ink: #2b221a;
  --ink-soft: #6b5d4d;
  --line: #ddccaa;
  --accent: #a23e2b;
  --accent-approved: #3f6b4a;
  --cat-salgado: #b5651d;
  --cat-salada: #4c7a4e;
  --cat-doce: #a2445c;
  --status-bg: #f3d9c9;
  --status-ink: #7a2e1c;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1c1712;
    --surface: #26201a;
    --surface-alt: #2f271e;
    --ink: #f2e9da;
    --ink-soft: #b9ab97;
    --line: #423727;
    --accent: #e0785f;
    --accent-approved: #7fc491;
    --cat-salgado: #d98a44;
    --cat-salada: #7ab97e;
    --cat-doce: #d9829b;
    --status-bg: #4a2e22;
    --status-ink: #f3c7ae;
    color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #1c1712; --surface: #26201a; --surface-alt: #2f271e; --ink: #f2e9da;
  --ink-soft: #b9ab97; --line: #423727; --accent: #e0785f; --accent-approved: #7fc491;
  --cat-salgado: #d98a44; --cat-salada: #7ab97e; --cat-doce: #d9829b;
  --status-bg: #4a2e22; --status-ink: #f3c7ae; color-scheme: dark;
}}
:root[data-theme="light"] {{
  --bg: #efe6d3; --surface: #fffdf8; --surface-alt: #fbf1de; --ink: #2b221a;
  --ink-soft: #6b5d4d; --line: #ddccaa; --accent: #a23e2b; --accent-approved: #3f6b4a;
  --cat-salgado: #b5651d; --cat-salada: #4c7a4e; --cat-doce: #a2445c;
  --status-bg: #f3d9c9; --status-ink: #7a2e1c; color-scheme: light;
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--ink);
  font-family: "Work Sans", system-ui, sans-serif; font-weight: 380;
  line-height: 1.5; padding: 48px 20px 96px;
}}
.wrap {{ max-width: 760px; margin: 0 auto; }}

.masthead {{ margin-bottom: 40px; }}
.eyebrow {{
  font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--ink-soft); font-weight: 600; margin: 0 0 6px;
}}
h1 {{
  font-family: "Fraunces", serif; font-weight: 500; font-size: clamp(1.7rem, 4vw, 2.3rem);
  margin: 0 0 14px; text-wrap: balance; letter-spacing: -0.01em;
}}
.status-pill {{
  display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem;
  font-weight: 600; padding: 5px 14px; border-radius: 999px;
  background: var(--status-bg); color: var(--status-ink);
}}
.status-pill::before {{ content: "●"; font-size: 0.6rem; }}
.howto {{
  margin-top: 18px; font-size: 0.92rem; color: var(--ink-soft);
  border-left: 2px solid var(--line); padding-left: 14px;
}}

.day {{ margin-bottom: 44px; }}
.day-head {{
  display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px;
  border-bottom: 1px solid var(--line); padding-bottom: 8px;
}}
.day .weekday {{ font-family: "Fraunces", serif; font-size: 1.3rem; font-weight: 500; }}
.day .date {{ font-size: 0.85rem; color: var(--ink-soft); }}

.slot {{
  background: var(--surface); border-radius: 14px; padding: 18px 20px;
  margin-bottom: 14px; border: 1px solid var(--line);
}}
.slot-head {{ display: flex; align-items: baseline; gap: 10px; margin-bottom: 12px; }}
.slot-name {{ font-weight: 650; font-size: 0.95rem; }}
.slot-sub {{ font-size: 0.78rem; color: var(--ink-soft); }}

.filmstrip {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; align-items: flex-start; }}
.item {{ margin: 0; width: 108px; }}
.item-video {{ width: 190px; }}
.thumb {{ position: relative; border-radius: 8px; overflow: hidden; background: var(--surface-alt); }}
.thumb-media {{ width: 100%; display: block; }}
.item .thumb-media {{ height: 140px; object-fit: cover; }}
.item-video .thumb-media {{ height: 240px; background: #000; }}
.no-thumb {{ width: 108px; height: 140px; display: flex; align-items: center; justify-content: center; font-size: 0.68rem; color: var(--ink-soft); text-align: center; padding: 8px; }}
.cat-tag {{
  display: block; margin-top: 5px; font-size: 0.68rem; font-weight: 600;
  text-align: center; letter-spacing: 0.02em;
}}
.cat-tag.cat-salgado {{ color: var(--cat-salgado); }}
.cat-tag.cat-salada {{ color: var(--cat-salada); }}
.cat-tag.cat-doce {{ color: var(--cat-doce); }}

.ticket {{
  white-space: pre-wrap; font-family: "Work Sans", sans-serif; font-size: 0.88rem;
  background: var(--surface-alt); border-radius: 8px; padding: 14px 16px;
  margin: 12px 0 0; color: var(--ink);
}}

footer {{
  max-width: 760px; margin: 56px auto 0; padding-top: 20px;
  border-top: 1px solid var(--line); font-size: 0.8rem; color: var(--ink-soft);
}}
</style></head>
<body>
  <div class="wrap">
    <div class="masthead">
      <p class="eyebrow">Bernardino Restaurante — cronograma de postagens</p>
      <h1>Semana de {fmt_date_long(plan["week_start"])} a {fmt_date_long(week_end)}</h1>
      <span class="status-pill">{status_label}</span>
      <p class="howto">Revise as fotos, vídeos e legendas abaixo. Se estiver tudo certo, responda "aprovado" no chat — o cronograma inteiro entra na fila de publicação automática da semana. Se algo precisar mudar, diga o que ajustar.</p>
    </div>
    {days_html}
  </div>
  <footer>Gerado automaticamente a partir do conteúdo já selecionado e reservado para esta semana — nada foi publicado ainda.</footer>
</body></html>'''

    out_path = plan_path.replace(".json", "_gallery.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(out_path)


if __name__ == "__main__":
    main()
