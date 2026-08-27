"""Persist raw response bodies so analysis never needs a re-crawl."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_EXT_BY_TYPE = {
    "text/html": ".html",
    "text/css": ".css",
    "application/javascript": ".js",
    "text/javascript": ".js",
    "application/json": ".json",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}


class Storage:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.pages_dir = self.root / "pages"
        self.pages_dir.mkdir(parents=True, exist_ok=True)

    def save_body(self, url: str, content_type: str, body: bytes) -> Path:
        digest = hashlib.sha1(url.encode()).hexdigest()[:12]
        parts = urlsplit(url)
        stem = _SAFE.sub("_", f"{parts.path}{('_' + parts.query) if parts.query else ''}").strip("_")
        stem = (stem or "root")[:80]
        ext = _EXT_BY_TYPE.get(content_type, "")
        path = self.pages_dir / f"{stem}.{digest}{ext}"
        path.write_bytes(body)
        return path

    def write_json(self, name: str, data: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(data, indent=2, sort_keys=True))
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text)
        return path
