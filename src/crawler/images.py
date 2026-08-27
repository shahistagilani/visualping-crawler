"""Optional image inspection.

Two escalations the byte/metadata scan can't cover:

* **OCR** — for a target *drawn in the pixels*. Best-effort: needs Pillow and
  ``pytesseract`` plus a ``tesseract`` binary on PATH; returns ``[]`` if any of
  those is missing, so the crawler degrades gracefully.
* **Outlier flagging** — an image whose dimensions stand out (a wide banner
  among small icons) is the classic place a target is rendered as text. When OCR
  isn't available or finds nothing, such images are listed for manual review.
"""

from __future__ import annotations

import io
import re
import shutil

from .scanner import PASSWORD_RE

_OUTLIER_RATIO = 3.0
_OUTLIER_MAX_DIM = 256
_UPSCALE = 4


def ocr_matches(body: bytes) -> list[str]:
    """Strict target matches read out of an image's pixels, or ``[]``."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return []
    if shutil.which("tesseract") is None:
        return []
    try:
        image = Image.open(io.BytesIO(body)).convert("L")
        image = image.resize((image.width * _UPSCALE, image.height * _UPSCALE))
        text = pytesseract.image_to_string(image)
    except Exception:
        return []
    collapsed = re.sub(r"\s+", "", text)
    return list(dict.fromkeys(PASSWORD_RE.findall(collapsed)))


def outlier_reason(body: bytes) -> str | None:
    """A human-readable reason to eyeball this image, or ``None``."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(body)) as image:
            width, height = image.size
    except Exception:
        return None
    if not width or not height:
        return None
    if max(width, height) / min(width, height) >= _OUTLIER_RATIO:
        return f"unusual aspect ratio {width}x{height} — check for text drawn in the image"
    if max(width, height) >= _OUTLIER_MAX_DIM:
        return f"large image {width}x{height} — check for text drawn in the image"
    return None
