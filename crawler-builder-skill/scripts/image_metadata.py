"""Reusable image-metadata scanner for pattern-detection crawlers.

Images carry text channels most crawlers never open — and in real crawls those
channels hold a large share of targets. This reads them all with Pillow and
runs the target pattern (through the full text ladder, incl. utf-16) over every
field:

  - EXIF tags, including the Exif sub-IFD's UserComment (often UTF-16!)
  - JPEG COM comment markers
  - PNG tEXt / iTXt / zTXt text chunks

It also handles the BARE-BODY case: a metadata field whose ENTIRE value is the
target's body without its wrapper (e.g. the inner hex, no `ABCDEF{...}`).
Because a bare body is a weaker signal than a wrapped match, a per-image rule
applies: if an image already yields a properly-wrapped target, its bare-body
fields are treated as decoys; a bare body is promoted only when its image has
no wrapped target. (Documented heuristic — see decoys-and-pitfalls.md.)

Requires Pillow (`pip install Pillow`). Degrades to an empty result if Pillow
is missing or the bytes aren't a decodable image, so callers can always fall
back to a raw-byte scan.

Usage as a library:
    import re
    from image_metadata import find_pattern_in_image
    PAT  = re.compile(r"ABCDEF\\{[0-9a-fA-F]{16}\\}")   # wrapped form
    BARE = re.compile(r"^[0-9a-fA-F]{16}$")             # bare body (optional)
    hits = find_pattern_in_image(img_bytes, PAT, bare_body=BARE, wrap=("ABCDEF{", "}"))

Usage from the shell:
    python image_metadata.py 'ABCDEF\\{[0-9a-fA-F]{16}\\}' image.jpg \\
        --bare '^[0-9a-fA-F]{16}$' --wrap 'ABCDEF{' '}'
"""
from __future__ import annotations

import argparse
import re
import sys

# Reuse the text ladder so metadata fields get utf-16 / entity / base64 / etc.
try:
    from text_representations import find_pattern
except ImportError:  # allow running from another directory
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from text_representations import find_pattern


def _decodings(value):
    """Yield candidate string views of one metadata value (bytes or str)."""
    if isinstance(value, bytes):
        for enc in ("utf-16-le", "utf-16-be", "latin-1", "utf-8"):
            yield value.decode(enc, "ignore")
    elif isinstance(value, str):
        yield value


def _field_values(image) -> list:
    """Collect every metadata field value from an opened Pillow image."""
    values: list = []
    try:
        from PIL.ExifTags import Base
        exif = image.getexif()
        values.extend(exif.values())                       # IFD0 tags
        try:
            values.extend(exif.get_ifd(Base.ExifOffset.value).values())  # UserComment etc.
        except Exception:
            pass
    except Exception:
        pass
    # JPEG COM marker + PNG tEXt/iTXt chunks both surface via image.info.
    values.extend((image.info or {}).values())
    return values


def find_pattern_in_image(
    data: bytes,
    pattern: re.Pattern,
    bare_body: re.Pattern | None = None,
    wrap: tuple[str, str] | None = None,
) -> set[str]:
    """Scan an image's metadata for `pattern` (wrapped form). If `bare_body`
    and `wrap` are given, a field whose entire value matches `bare_body` is
    promoted to `wrap[0] + body + wrap[1]` — but only for images that yield NO
    wrapped match (formatted-beats-bare, per image). Returns empty if Pillow is
    absent or the bytes aren't an image."""
    try:
        import io
        from PIL import Image
    except ImportError:
        return set()
    try:
        image = Image.open(io.BytesIO(data))
    except Exception:
        return set()

    full: set[str] = set()
    bare: set[str] = set()
    for value in _field_values(image):
        for text in _decodings(value):
            full |= find_pattern(text, pattern)
            if bare_body is not None and wrap is not None:
                stripped = text.strip().strip("\x00").strip()
                if bare_body.match(stripped):
                    bare.add(f"{wrap[0]}{stripped}{wrap[1]}")

    # Formatted beats bare: trust bare bodies only when nothing wrapped exists.
    return full if full else bare


def _main() -> int:
    ap = argparse.ArgumentParser(description="Scan image metadata for a target pattern.")
    ap.add_argument("pattern", help="regex for the wrapped target form")
    ap.add_argument("image", help="path to the image file")
    ap.add_argument("--bare", help="regex matching a bare body (whole field)")
    ap.add_argument("--wrap", nargs=2, metavar=("PREFIX", "SUFFIX"),
                    help="wrapper to apply to a promoted bare body")
    args = ap.parse_args()

    with open(args.image, "rb") as fh:
        data = fh.read()
    bare = re.compile(args.bare) if args.bare else None
    wrap = tuple(args.wrap) if args.wrap else None
    hits = find_pattern_in_image(data, re.compile(args.pattern), bare_body=bare, wrap=wrap)
    for hit in sorted(hits):
        print(hit)
    return 0 if hits else 1


if __name__ == "__main__":
    raise SystemExit(_main())
