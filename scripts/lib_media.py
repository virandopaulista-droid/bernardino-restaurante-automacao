"""Shared helpers for scanning Bernardino Restaurante's Drive media folders,
converting HEIC to JPEG, and reading/writing the classification manifest.
"""
import json
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CONVERTED_DIR = PROJECT_DIR / "content" / "converted"
MANIFEST_PATH = PROJECT_DIR / "content" / "media_manifest.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO_EXTS = {".mp4", ".mov"}
SKIP_DIR_NAMES = {"usados", "usadas"}
# "Stories Reels" holds old/test videos, not real reel candidates (user
# confirmed 2026-07-27) -- excluded from video selection only, images in
# other folders are unaffected.
SKIP_DIR_NAMES_VIDEO = SKIP_DIR_NAMES | {"stories reels"}

CATEGORIES = ["prato_salgado", "salada", "doce", "ambiente", "outro"]

# Fixed footer block, appended to the end of every feed/reel caption (never
# left to the AI to reproduce — user asked 2026-07-27 for guaranteed
# consistency; originally placed at the top, corrected to the end same day).
FIXED_CAPTION_FOOTER = (
    "📍 Rua Bernardino de Campos, 201 — Brooklin/Campo Belo, SP\n"
    "⏰ Segunda a sexta, 11h30 às 15h\n"
    "👉 Venha almoçar com a gente!"
)

# Fixed hashtag block — appended after FIXED_CAPTION_FOOTER as the very last
# line of feed/reel captions (never left to the AI: guaranteed exact text and
# guaranteed position, user asked 2026-07-27 for hashtags to always be the
# last line, after the footer, not before it).
FIXED_HASHTAGS = (
    "#bernardinorestaurante #restauranteacampo #brooklinsp #campobelosp "
    "#almoçosp #comidacaseira #buffetporkilo #restaurantesp"
)


def _env_dirs():
    """Reads MEDIA_DIR_* from the already-sourced environment (.env is
    sourced by the calling shell script before this runs)."""
    return {
        "images_2025": os.environ.get("MEDIA_DIR_IMAGES_2025", ""),
        "images_2026": os.environ.get("MEDIA_DIR_IMAGES_2026", ""),
        "videos": os.environ.get("MEDIA_DIR_VIDEOS", ""),
        "stories_reels": os.environ.get("MEDIA_DIR_STORIES_REELS", ""),
    }


def _walk_media(root, exts, skip_dir_names=SKIP_DIR_NAMES):
    root = Path(root)
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.strip().lower() not in skip_dir_names]
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext in exts:
                yield Path(dirpath) / name


def iter_image_files():
    """Yields every candidate image (Imagens tratadas 2025/2026 + Stories Reels
    dump), skipping any 'Usados'/'Usadas' subfolder."""
    dirs = _env_dirs()
    seen = set()
    for key in ("images_2025", "images_2026", "stories_reels"):
        for path in _walk_media(dirs[key], IMAGE_EXTS):
            resolved = str(path.resolve())
            if resolved not in seen:
                seen.add(resolved)
                yield path


def iter_video_files():
    """Yields every candidate video from Vídeos Tratados' month folders,
    skipping 'Usados' and 'Stories Reels' (old/test content, not real reel
    candidates -- confirmed with the user 2026-07-27)."""
    dirs = _env_dirs()
    seen = set()
    for path in _walk_media(dirs["videos"], VIDEO_EXTS, skip_dir_names=SKIP_DIR_NAMES_VIDEO):
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            yield path


def convert_heic_to_jpeg(src_path: Path) -> Path:
    """Converts a file named *.heic to JPEG under content/converted/, reusing
    an existing conversion if already done. Returns the JPEG path.

    Some files synced from the client's Drive carry a .HEIC extension but are
    actually plain JPEGs inside (observed 2026-07-27, e.g. IMG_9181.HEIC has a
    JFIF/JPEG header) — likely a phone/Drive sync quirk. Falls back to a
    normal PIL open (format-sniffed from content, not extension) in that case,
    so the output is always a real JPEG regardless of what's really inside.
    """
    from PIL import Image

    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CONVERTED_DIR / (src_path.stem + ".jpg")
    if out_path.exists():
        return out_path

    try:
        import pillow_heif
        heif_file = pillow_heif.read_heif(str(src_path))
        image = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data)
    except Exception:
        image = Image.open(src_path)

    image.convert("RGB").save(out_path, format="JPEG", quality=92)
    return out_path


def resolve_classifiable_path(src_path: Path) -> Path:
    """Returns a path safe to feed to a vision model for classification/
    captioning: HEIC gets converted to JPEG, everything else (jpg/png/webp)
    passes through as-is (OpenAI vision and CLIP both accept webp directly).
    NOT guaranteed safe for Facebook/Instagram upload — use
    ensure_upload_ready() for that."""
    if src_path.suffix.lower() == ".heic":
        return convert_heic_to_jpeg(src_path)
    return src_path


def ensure_upload_ready(src_path: Path) -> Path:
    """Returns a JPEG path safe to upload to Facebook/Instagram. Facebook's
    classic /photos endpoint and Instagram's Content Publishing API are not
    guaranteed to accept .webp or (mislabeled) .heic, so anything that isn't
    already a plain .jpg/.jpeg gets normalized to JPEG under content/converted/
    (reusing convert_heic_to_jpeg's PIL-based fallback path for non-HEIC
    formats too)."""
    ext = src_path.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        return src_path
    if ext == ".heic":
        return convert_heic_to_jpeg(src_path)

    from PIL import Image

    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CONVERTED_DIR / (src_path.stem + ".jpg")
    if out_path.exists():
        return out_path
    image = Image.open(src_path)
    image.convert("RGB").save(out_path, format="JPEG", quality=92)
    return out_path


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"images": []}


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def indexed_by_source(manifest: dict) -> set:
    return {entry["source_path"] for entry in manifest["images"]}


_FFPROBE_FALLBACK = (
    "C:/Users/Robso/AppData/Local/Microsoft/WinGet/Packages/"
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.2-full_build/bin/ffprobe.exe"
)


def get_video_duration_seconds(path) -> float:
    """Returns the real duration of a video file via ffprobe. Raises if
    ffprobe can't read it (corrupt file, unsupported codec, etc.) — callers
    should treat that as 'skip this video', not crash the whole run."""
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe") or _FFPROBE_FALLBACK
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return float(result.stdout.strip())


def get_audio_mean_volume_db(path) -> float:
    """Returns the mean audio volume in dB via ffmpeg's volumedetect filter.
    Raises if there's no audio stream at all or ffmpeg can't read the file —
    callers should treat that as 'skip this video' too, same as duration.
    A real (non-silent) clip typically sits well above -40dB; a client video
    found 2026-07-27 with a present-but-silent AAC track measured -91dB."""
    import re
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg") or _FFPROBE_FALLBACK.replace("ffprobe.exe", "ffmpeg.exe")
    result = subprocess.run(
        [ffmpeg, "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=30,
    )
    match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", result.stderr)
    if not match:
        raise ValueError(f"nao encontrei audio stream / mean_volume na saida do ffmpeg para {path}")
    return float(match.group(1))


def append_image_entry(entry: dict) -> None:
    """Reloads the manifest fresh from disk, adds this one entry, and saves —
    instead of holding one big in-memory copy across a long batch run. A
    long-running classifier that instead loads once and appends in memory
    will, on every save, silently overwrite any 'used' flag another process
    (e.g. select_media.py) set on an earlier entry in the meantime, since its
    stale in-memory copy still has that entry unused. Reloading right before
    each write keeps the race window to a single append instead of an entire
    run."""
    manifest = load_manifest()
    manifest["images"].append(entry)
    save_manifest(manifest)
