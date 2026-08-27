"""Reusable decoding ladder for pattern-detection crawlers.

Given a compiled target pattern, this scans text (and raw bytes) through the
bounded ladder of lightweight, reversible representations that real targets
hide behind: charset views (latin-1, utf-16), HTML/URL/CSS/JS unescaping,
base64/base32/hex token decoding, and character-code arrays. It is the
written-out answer to "Q2: what could I do to this text to make a naive scan
miss it while the site can still use it?"

Design notes (why it's shaped this way):
- Every transform is SYNTAX-GATED and LENGTH-BOUNDED so decoding random noise
  can't explode into exponential work or spurious matches.
- Decoding is single-layer by default. Nesting is a deliberate escalation.
- Keep your target PATTERN specific (fixed prefix + exact body shape). A tight
  pattern makes a false positive on transformed noise effectively impossible;
  a loose pattern makes this whole file dangerous.
- Reversed / ROT13 are late, situational rungs.

Usage as a library:
    import re
    from text_representations import find_pattern, find_pattern_in_bytes
    PAT = re.compile(r"ABCDEF\\{[0-9a-fA-F]{16}\\}")
    hits = find_pattern(html_text, PAT)
    hits |= find_pattern_in_bytes(response_content, PAT)

Usage from the shell:
    python text_representations.py 'ABCDEF\\{[0-9a-fA-F]{16}\\}' path/to/file
    cat file | python text_representations.py 'ABCDEF\\{[0-9a-fA-F]{16}\\}' -
"""
from __future__ import annotations

import base64
import binascii
import codecs
import html
import re
import sys
from urllib.parse import unquote

# --- token shapes worth attempting to decode (bounded to avoid noise) --------
_B64_TOKEN = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")
_HEX_TOKEN = re.compile(r"[0-9a-fA-F]{24,}")
_CHARCODE_SEQ = re.compile(
    r"(?:0x[0-9a-fA-F]+|\d{1,3})(?:\s*,\s*(?:0x[0-9a-fA-F]+|\d{1,3})){9,}"
)
_CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})\s?")
_HEX_ESCAPE = re.compile(r"\\x([0-9a-fA-F]{2})")
_UNI_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _reencoded_views(text: str):
    """Whole-text reversible transforms. Each undoes one common obfuscation."""
    yield html.unescape(text)                                    # &#65;BCDEF...
    yield unquote(text)                                          # %41BCDEF...
    yield _CSS_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)   # \41 ...
    yield _HEX_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)   # \x41 ...
    yield _UNI_ESCAPE.sub(lambda m: chr(int(m.group(1), 16)), text)   # \u0041 ...
    # Late, situational rungs — cheap enough to keep, rarely needed:
    yield text[::-1]                                            # reversed
    yield codecs.decode(text, "rot_13")                        # ROT13


def _decoded_tokens(text: str):
    """Decoded content of base64/hex tokens embedded in the text."""
    for tok in _B64_TOKEN.findall(text):
        cand = tok.replace("-", "+").replace("_", "/")
        cand += "=" * (-len(cand) % 4)
        try:
            yield base64.b64decode(cand, validate=False).decode("latin-1")
        except (binascii.Error, ValueError):
            pass
    for tok in _HEX_TOKEN.findall(text):
        even = tok if len(tok) % 2 == 0 else tok[:-1]
        try:
            yield bytes.fromhex(even).decode("latin-1")
        except ValueError:
            pass


def _charcode_decodes(text: str):
    """Strings decoded from character-code arrays: [65,66,...] / fromCharCode."""
    for match in _CHARCODE_SEQ.findall(text):
        try:
            nums = re.split(r"\s*,\s*", match)
            yield "".join(
                chr(int(n, 16) if n.lower().startswith("0x") else int(n)) for n in nums
            )
        except (ValueError, OverflowError):
            pass


def find_pattern(text: str, pattern: re.Pattern) -> set[str]:
    """Return every match of `pattern` in `text` or any single-layer decoding."""
    found: set[str] = set(pattern.findall(text))
    for view in _reencoded_views(text):
        found.update(pattern.findall(view))
    for decoded in _decoded_tokens(text):
        found.update(pattern.findall(decoded))
    for decoded in _charcode_decodes(text):
        found.update(pattern.findall(decoded))
    return found


def find_pattern_in_bytes(data: bytes, pattern: re.Pattern) -> set[str]:
    """Scan raw bytes for the pattern under the charset views that matter:
    latin-1 (1:1, ASCII-safe) and utf-16 LE/BE (two-bytes-per-char values,
    e.g. an EXIF UserComment — the \\x00-between-chars case latin-1 misses).
    Each view is then run through the full text ladder."""
    if not data:
        return set()
    found: set[str] = set()
    for enc in ("latin-1", "utf-16-le", "utf-16-be"):
        found |= find_pattern(data.decode(enc, "ignore"), pattern)
    return found


def _main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    pattern = re.compile(argv[1])
    if argv[2] == "-":
        data = sys.stdin.buffer.read()
    else:
        with open(argv[2], "rb") as fh:
            data = fh.read()
    hits = find_pattern_in_bytes(data, pattern)
    for hit in sorted(hits):
        print(hit)
    return 0 if hits else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
