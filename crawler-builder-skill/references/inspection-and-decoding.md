# Inspection & Decoding: Recognizing the Target in Any Representation

This is the detailed, code-writing version of *"try every disguise"* from the main guide. A file can *contain* what you're looking for and still show nothing to a plain search — because it's encoded, split across tags, stored in an unexpected character format, or tucked into a file's info fields. If this list ever feels incomplete, go back to the plain question — *"what disguise would slip past the exact search I'm running right now?"* — and add that rung.

## Table of contents
- [Three inspection layers](#three-inspection-layers)
- [The representation ladder (with reasons)](#the-representation-ladder-with-reasons)
- [Guardrails that keep decoding reliable](#guardrails-that-keep-decoding-reliable)
- [Non-obvious carriers of the target](#non-obvious-carriers-of-the-target)
- [Image metadata (high value, usually missed)](#image-metadata-high-value-usually-missed)
- [The unwrapped-body case](#the-unwrapped-body-case)
- [Binary, documents, and OCR (staged)](#binary-documents-and-ocr-staged)
- [Match semantics and provenance](#match-semantics-and-provenance)

## Three inspection layers

Every successful, in-scope response passes a cheap universal scan before type-specific work.

**Layer 1 — Universal (runs on everything, every status).**
- Match on **raw response bytes** (not a decoded-text view).
- Inspect headers: `Location`, `Link`, `Content-Location`, `Refresh`, `Content-Disposition`, custom `X-*`.
- Scan **redirect-hop bodies** and **error-page bodies** (401/403/404/500) — don't `continue` past non-200s before scanning.
- Record status, final URL, content-type, length, encoding, redirect chain, content hash. Enforce a max body size; stream; log oversized skips.

Raw-byte matching is non-negotiable: a decoded-text convenience view guesses an encoding, can substitute replacement characters, and mangles binary.

**Layer 2 — Type-aware parsing.** Classify by MIME **and** extension **and** magic bytes **and** parseability (never MIME alone — servers lie). Extract URLs and searchable text per type (HTML DOM + `srcset`/forms/meta; CSS `url()`/`@import`; JS source + maps + literals; JSON recursive strings; XML/SVG nodes; sitemap/manifest entries).

**Layer 3 — Structured & reconstructed text.** Search **both** raw source **and** text reconstructed from the parse. For HTML/XML keep two forms:
- natural text with whitespace (best for phrase/keyword matching), and
- **adjacent text-node concatenation** — catches markup-split targets like `ABC<span>DEF</span>`.

## The representation ladder (with reasons)

Climb cheapest-first. Each rung recovers a target the rungs above it miss.

| Rung | Recovers | Note |
|---|---|---|
| literal on raw bytes | plain ASCII targets | baseline |
| **latin-1 view** | ASCII target inside binary | 1:1 byte→char, never corrupts ASCII |
| **utf-16 LE/BE view** | text stored two-bytes-per-char | the sleeper — a `\x00` between chars defeats latin-1 and literal scans (e.g. an EXIF UserComment) |
| declared text decode | correctly-charset text | after validating the charset |
| parsed text + adjacent nodes | markup-split targets | Layer 3 |
| HTML-entity unescape | `&#65;BCDEF` | |
| percent-decode | `%41BCDEF` | |
| JS `\xNN` / `\uNNNN` unescape | string-escaped values | |
| CSS `\NN` unescape | `content:"...\7B..."` | |
| base64 / base32 / hex of substrings | encoded blobs | decode only plausible tokens |
| **char-code arrays** | `[65,66,...]` / `String.fromCharCode(...)` | decimal **and** `0x` hex |
| reversed / ROT13 | deliberately scrambled | **late, situational** — not a default |

`scripts/text_representations.py` implements this generically. Import it; pass your own compiled pattern.

## Guardrails that keep decoding reliable

Aggressive decoding is a false-positive factory and can blow up runtime:
- **Bound depth and length.** One decode layer by default; recurse only on evidence with a hard cap. Cap candidate token length.
- **Syntax-gate every transform.** Base64-decode only base64-shaped tokens above a min length; a char-code decode needs a long-enough run of in-range integers. Don't decode English prose.
- **Make the target regex specific.** A fixed prefix + exact body shape makes a spurious match on transformed noise effectively impossible.
- **De-dup representations by hash** before matching.
- **Record the transform chain** in provenance (`raw-bytes → base64 → utf-8`).
- **Validate at the end** against the strict rule — where near-misses and decoys get rejected.

## Non-obvious carriers of the target

Beyond page-body text: **headers & cookies** (note some briefs designate header values as decoys — read the rules); **redirect-hop bodies**; **error-page bodies**; **adjacent resources** (CSS, JS, source maps, `sitemap.xml`, manifest, favicon); **image metadata** (next).

## Image metadata (high value, usually missed)

Images carry text channels most crawlers never open — in real crawls they've held a large share of targets. Read:
- **EXIF** tags — especially **`UserComment`** (frequently UTF-16-encoded; see the ladder), plus `ImageDescription`, `XPComment`, `Artist`, `Copyright`.
- **JPEG `COM`** comment markers.
- **PNG `tEXt` / `iTXt` / `zTXt`** text chunks.

`scripts/image_metadata.py` extracts all of these with Pillow and runs the full text ladder (incl. utf-16) on each field.

**Metadata ≠ pixels.** Text *rendered into the image itself* (a banner, a screenshot, a photographed whiteboard) is invisible to every byte/metadata scan — that needs OCR (staged, optional). Don't add a heavyweight native OCR dependency for one target without cause; instead **document the known image + its value** as a stated, reasoned gap, and offer OCR as an opt-in that degrades to a no-op when the engine is absent.

## The unwrapped-body case

When the target has a wrapper (a prefix/brackets), you'll sometimes find just the **inner body**, bare, in a comment or metadata field. Treat a field whose *entire* value is exactly the inner shape as a **candidate** (wrap it back to the canonical form), not a lookalike to discard.

But a bare body is a *weaker* signal than a wrapped one, so apply a **per-container rule**: if the *same* container (e.g. one image) already yields a properly-wrapped target, treat its bare-body fields as **decoys**; promote a bare body only when its container has nothing better. When genuinely ambiguous, surface it as a candidate with its evidence and let validation decide. (`scripts/image_metadata.py` implements this — pass a `bare_body` pattern and `wrap`.)

## Binary, documents, and OCR (staged)

Stage cost — don't deep-analyze everything up front:
1. **Always:** raw-byte scan (bounded) + image metadata.
2. **When applicable:** document text (PDF/Office), archive listings.
3. **Only after the normal crawl plateaus, with strict size/depth limits:** OCR images, inspect archive members.

Never auto-unpack nested/untrusted archives without limits. Defend against decompression bombs with caps on compressed size, uncompressed size, member count, and nesting depth.

## Match semantics and provenance

Decide up front (the detection contract): case/Unicode normalization; whether matches inside larger tokens count; whether the target must be visible text, source, decoded data, or *any* representation; expected count if known.

Store an immutable finding record:

```json
{
  "match": "ABCDEF{0123456789abcdef}",
  "source_url": "https://approved.example/assets/app.js",
  "final_url":  "https://approved.example/assets/app.js",
  "discovered_from": "https://approved.example/",
  "discovery_method": "script-src",
  "representation": "raw-bytes",         // or "utf-16", "exif:UserComment", "base64→utf-8", "bare-body:jpeg-com", ...
  "content_type": "application/javascript",
  "status": 200,
  "response_sha256": "…",
  "observed_at": "…Z"
}
```

De-duplicate the **match value** for the final answer, but keep **all** sightings — multiple independent sources validate a result and expose a broken extractor.
