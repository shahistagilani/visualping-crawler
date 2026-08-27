"""Target detection.

Scans a response for ``VISUALPING{<16 hex>}`` across the representations real
targets hide behind:

* the body decoded as UTF-8, latin-1, and **UTF-16 LE/BE**;
* HTML entities and ``\\xNN`` / ``\\uNNNN`` escapes;
* base64 / long-hex tokens embedded in the text;
* **decimal / hex character-code arrays** (``[86, 73, 83, ...]`` →
  ``String.fromCharCode``);
* for binary resources, a bare 16-hex token in metadata — promoted to the
  wrapped form **only when that resource yields no properly-wrapped match**
  (formatted beats bare, per resource).

Response headers are scanned too, but every header hit is marked *unqualified*
per the site's stated rule that header values are staging placeholders.
"""

from __future__ import annotations

import base64
import binascii
import html
import re
from dataclasses import dataclass

from .config import EXAMPLE_PASSWORD

PASSWORD_RE = re.compile(r"VISUALPING\{[0-9a-f]{16}\}")

_BARE_HEX_RE = re.compile(rb"(?<![0-9a-fA-Fx])[0-9a-f]{16}(?![0-9a-fA-F])")
_B64_TOKEN = re.compile(r"[A-Za-z0-9+/]{32,}={0,2}")
_HEX_TOKEN = re.compile(r"[0-9a-fA-F]{40,}")
_CHARCODE_SEQ = re.compile(
    r"(?:0x[0-9a-fA-F]{1,2}|\d{1,3})(?:\s*,\s*(?:0x[0-9a-fA-F]{1,2}|\d{1,3})){9,}"
)
_HEX_ESCAPE = re.compile(r"\\x([0-9a-fA-F]{2})")
_UNI_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")
_TEXT_TYPES = ("text/", "javascript", "ecmascript", "json", "xml", "svg", "css")


@dataclass(frozen=True)
class Finding:
    password: str
    source_url: str
    location: str
    qualified: bool  # False => does not count toward the target total (e.g. headers)


def scan(url: str, content_type: str, headers: dict[str, str], body: bytes) -> list[Finding]:
    qualified: dict[str, str] = {}  # password -> location (first hit wins)
    header_hits: dict[str, str] = {}

    def keep(store: dict[str, str], password: str, location: str) -> None:
        if password != EXAMPLE_PASSWORD:
            store.setdefault(password, location)

    for view_label, text in _text_views(body):
        for how, password in _matches_via_ladder(text):
            keep(qualified, password, _body_location(view_label, how))

    for name, value in headers.items():
        for match in PASSWORD_RE.finditer(str(value)):
            keep(header_hits, match.group(0), f"response header: {name}")

    # Bare 16-hex in binary metadata — only when nothing wrapped was found here.
    if not _is_text(content_type) and not qualified:
        for match in _BARE_HEX_RE.finditer(body):
            keep(
                qualified,
                f"VISUALPING{{{match.group(0).decode('ascii')}}}",
                "binary metadata (bare 16-hex, unwrapped)",
            )

    findings = [Finding(pw, url, loc, True) for pw, loc in qualified.items()]
    findings += [
        Finding(pw, url, loc, False)
        for pw, loc in header_hits.items()
        if pw not in qualified
    ]
    return findings


# --- representation ladder ------------------------------------------------


def _text_views(body: bytes):
    yield "", body.decode("utf-8", "replace")
    yield "", body.decode("latin-1")
    yield "utf-16-le", body.decode("utf-16-le", "ignore")
    yield "utf-16-be", body.decode("utf-16-be", "ignore")


def _matches_via_ladder(text: str):
    """Yield ``(how, password)`` for every strict match in ``text`` or a
    single-layer decoding of it."""
    for match in PASSWORD_RE.finditer(text):
        yield "", match.group(0)
    for match in PASSWORD_RE.finditer(html.unescape(text)):
        yield "html-entities", match.group(0)
    unescaped = _UNI_ESCAPE.sub(
        lambda m: chr(int(m.group(1), 16)),
        _HEX_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text),
    )
    if unescaped != text:
        for match in PASSWORD_RE.finditer(unescaped):
            yield "escapes", match.group(0)
    for decoded in _decoded_tokens(text):
        for match in PASSWORD_RE.finditer(decoded):
            yield "base64/hex", match.group(0)
    for decoded in _charcode_strings(text):
        for match in PASSWORD_RE.finditer(decoded):
            yield "char-code array", match.group(0)


def _decoded_tokens(text: str):
    for token in _B64_TOKEN.findall(text):
        padded = token + "=" * (-len(token) % 4)
        try:
            yield base64.b64decode(padded, validate=False).decode("latin-1")
        except (binascii.Error, ValueError):
            pass
    for token in _HEX_TOKEN.findall(text):
        even = token if len(token) % 2 == 0 else token[:-1]
        try:
            yield bytes.fromhex(even).decode("latin-1")
        except ValueError:
            pass


def _charcode_strings(text: str):
    for seq in _CHARCODE_SEQ.findall(text):
        parts = re.split(r"\s*,\s*", seq.strip())
        try:
            yield "".join(
                chr(int(p, 16) if p.lower().startswith("0x") else int(p)) for p in parts
            )
        except (ValueError, OverflowError):
            continue


def _body_location(view_label: str, how: str) -> str:
    detail = ", ".join(part for part in (view_label, how) if part)
    return f"response body ({detail})" if detail else "response body"


def _is_text(content_type: str) -> bool:
    return any(token in content_type for token in _TEXT_TYPES)
