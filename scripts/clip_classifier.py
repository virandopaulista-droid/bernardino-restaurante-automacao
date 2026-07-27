"""Free, local, zero-shot image classifier for Bernardino Restaurante media,
using CLIP ViT-L/14 (openai/clip-vit-large-patch14) via transformers. Model
weights are downloaded once and cached locally (~/.cache/huggingface) — no
per-image API cost afterward.
"""
from PIL import Image

LABELS = {
    "prato_salgado": "a hot savory main dish with meat, rice, beans or a hot buffet tray, not raw vegetables",
    "salada": "a cold salad bar tray with raw lettuce, tomato, carrot, chickpeas or grains, savory not sweet, no sauce or cream",
    "doce": "a sweet dessert like pudding, mousse, cake or sliced fruit arranged for dessert, sugary and creamy",
    "ambiente": "a restaurant dining room with tables and chairs, no food close up",
    "outro": "a person, a logo, or something unrelated to food",
}
_KEYS = list(LABELS.keys())
_TEXTS = list(LABELS.values())

_model = None
_processor = None


def _load():
    global _model, _processor
    if _model is None:
        import torch  # noqa: F401 (ensures torch backend is available)
        from transformers import CLIPModel, CLIPProcessor
        _model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14")
        _processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
    return _model, _processor


def classify(image_path) -> tuple:
    """Returns (category, confidence) for the given image path."""
    import torch

    model, processor = _load()
    img = Image.open(image_path).convert("RGB")
    inputs = processor(text=_TEXTS, images=img, return_tensors="pt", padding=True)
    with torch.no_grad():
        outputs = model(**inputs)
    probs = outputs.logits_per_image.softmax(dim=1)[0]
    best_idx = int(probs.argmax().item())
    return _KEYS[best_idx], round(float(probs[best_idx]), 3)
