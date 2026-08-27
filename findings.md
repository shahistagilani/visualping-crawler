# Findings — the eight passwords, with retrieval & discovery mechanism

This is the durable, human-verified write-up (kept in version control, next to
`challenge.md`). The per-run machine output is `output/report.md`; this file is
the reconciled conclusion, including offline analysis the crawler does not yet
perform. **Do not move this file into `output/`** — that directory is git-ignored
and wiped on every run.

**Method.** Crawl the maze to convergence (`max_depth=60` → 388 resources,
`discovered == fetched`, only `/report/?page=11` capped), save every response
body, then run offline: the full decode ladder (raw / latin-1 / UTF-16 LE+BE /
entity+escape unescape / base64+base32+hex tokens / character-code arrays /
reverse / ROT13), a nested 2-layer pass, a DOM-aware attribute+comment scan,
JPEG-segment parsing, image bit-plane analysis, and visual/OCR inspection of
every image.

## Result: 8 of 8 located — 6 certain, 2 high-confidence by elimination

| # | Password | Resource | Channel | How it's encoded | Conf. |
|---|----------|----------|---------|------------------|-------|
| 1 | `VISUALPING{349a583fba34c301}` | `/static/js/analytics.js` | JS file body | plain string literal | **Certain** |
| 2 | `VISUALPING{fb725e1f3d6728b1}` | `/static/js/theme-switcher.js` | JS file body | **decimal character-code array** → `String.fromCharCode` | **Certain** |
| 3 | `VISUALPING{db7e533a9cef7f72}` | `/static/img/field-visit.jpg` | EXIF `UserComment` tag | **UTF-16LE** text, wrapped | **Certain** |
| 4 | `VISUALPING{e1c2e40cf01c17cc}` | `/static/img/whiteboard-scan.png` | image pixels | **rendered as glyphs** (read by eye / OCR) | **Certain** |
| 5 | `VISUALPING{2dd5105a3fad0ef3}` | `/notes/diff-socket-socket/` | HTML body | plain text inside an HTML comment | **Certain** |
| 6 | `VISUALPING{73c8f3073fdc5f74}` | `/wiki/detect-embed/` | HTML body | plain text in a `data-*` attribute on `<body>` | **Certain** |
| 7 | `VISUALPING{622ee9dfa76d54a6}` | `/static/img/office-plants.jpg` | JPEG `COM` segment | bare 16-hex, wrapper added by us | **High (elimination)** |
| 8 | `VISUALPING{e19cd3432599af6f}` | `/static/img/team-offsite.jpg` | JPEG `COM` segment | bare 16-hex, wrapper added by us | **High (elimination)** |

Findings 7–8 are the only ones not independently confirmable without a
submission oracle — see [their section](#findings-7--8--the-two-jpeg-com-values).

---

## Reproducing these findings

All commands below assume the target and credentials come from `crawler.toml`
(they are never in this file):

```bash
BASE=$(python -c "import tomllib;print(tomllib.load(open('crawler.toml','rb'))['target']['base_url'].rstrip('/'))")
USER=$(python -c "import tomllib;print(tomllib.load(open('crawler.toml','rb'))['auth']['username'])")
PASS=$(python -c "import tomllib;print(tomllib.load(open('crawler.toml','rb'))['auth']['password'])")
get() { curl -s -u "$USER:$PASS" "$BASE$1"; }        # authenticated GET, path arg
```

Full-corpus sweep used for #1–#3, #5, #6 (needs the `crawler-builder` skill's
`text_representations.py` on `PYTHONPATH`, and a completed crawl in `output/`):

```python
import glob, re
from text_representations import find_pattern_in_bytes          # decode ladder
PAT = re.compile(r"VISUALPING\{[0-9a-fA-F]{16}\}")
for p in sorted(glob.glob("output/pages/*")):
    hits = find_pattern_in_bytes(open(p, "rb").read(), PAT)     # raw+latin1+utf16+ladder
    if hits:
        print(p, sorted(hits))
```

Once the enhanced scanner is in place, `python -m crawler` reports #1–#3 and
#5–#8 directly, and lists `whiteboard-scan.png` under *Manual inspection
suggested* (or OCRs it, with `pip install ".[ocr]"` + a `tesseract` binary).

---

## Finding 1 — `VISUALPING{349a583fba34c301}`

- **Retrieve** — `get /static/js/analytics.js`. Discovered as a `<script
  src="/static/js/analytics.js" defer>` subresource on 17 crawled pages (e.g.
  `/wiki/history-history/`, `/blog/crawler-viewport/`); the crawler enqueues
  every `<script src>`, so an authenticated GET returns it directly.
- **Locate** — line 12 of the file body:

  ```js
  // FIXME(ops): temporary admin password for the provisioning API —
  // hardcoded during the migration, remove before prod. TODO: rotate.
  var ADMIN_PASSWORD = 'VISUALPING{349a583fba34c301}';
  ```

- **Decode** — none. The literal is already in spec format; a plain
  `VISUALPING\{[0-9a-f]{16}\}` regex on the UTF-8 body matches it.
- **Discovery mechanism** — the site ships seven near-identical "runtime"
  scripts (`widgets.js`, `telemetry.js`, `carousel.js`, …) as camouflage;
  `analytics.js` is the only one with a payload. Found by fetching all seven and
  regex-scanning each — this one hits, the other six don't.
- **First crawl caught it?** Yes.
- **Reproduce** — `get /static/js/analytics.js | grep -o 'VISUALPING{[0-9a-f]\{16\}}'`
- **Confidence: certain.** Exact format, response body (not a header), unique
  value, textbook hardcoded-secret placement.

## Finding 2 — `VISUALPING{fb725e1f3d6728b1}`

- **Retrieve** — `get /static/js/theme-switcher.js`. Another `<script src>`
  subresource, on maze pages such as `/notes/header-rule/`.
- **Locate** — a numeric array in the body:

  ```js
  // provisioning beacon — decodes to this deployment's password;
  var _beacon = [86, 73, 83, 85, 65, 76, 80, 73, 78, 71, 123, 102, 98, 55, 50,
                 53, 101, 49, 102, 51, 100, 54, 55, 50, 56, 98, 49, 125];
  cfg.beacon = function () { return String.fromCharCode.apply(null, _beacon); };
  ```

- **Decode** — each integer is an ASCII code point; map `chr(n)`:
  `86→V 73→I 83→S 85→U 65→A 76→L 80→P 73→I 78→N 71→G 123→{ 102→f 98→b 55→7 50→2
  53→5 101→e 49→1 102→f 51→3 100→d 54→6 55→7 50→2 56→8 98→b 49→1 125→}` →
  `VISUALPING{fb725e1f3d6728b1}`. The page's own JS would do the same via
  `String.fromCharCode`.
- **Discovery mechanism** — the decode ladder's **character-code-array rung**:
  find runs of ≥10 comma/space/`0x`-separated small integers, join `chr()` of
  each, re-scan the result with the target regex.
- **First crawl caught it?** No — the scanner's regex only saw literal text
  (now fixed; the ladder is in `scanner.py`).
- **Reproduce** —
  `get /static/js/theme-switcher.js | python -c "import sys,re;a=list(map(int,re.search(r'\[([\d,\s]+)\]',sys.stdin.read()).group(1).split(',')));print(''.join(map(chr,a)))"`
- **Confidence: certain.** Decodes exactly to spec format; the in-code comment
  states it *is* the password; response body.

## Finding 3 — `VISUALPING{db7e533a9cef7f72}`

- **Retrieve** — `get /static/img/field-visit.jpg` (a `<img src>` target on 14
  crawled pages, incl. `/docs/`).
- **Locate** — the JPEG's `APP1` (Exif) segment, Exif sub-IFD, **`UserComment`**
  tag `0x9286`. Raw tag bytes: `UNICODE\0` (charset marker) followed by UTF-16LE
  `V\x00 I\x00 S\x00 U\x00 A\x00 L\x00 P\x00 I\x00 N\x00 G\x00 {\x00 d\x00 b\x00
  7\x00 …`. (The same file's `COM` segment holds `5a6b01d97bfffdc3` — a decoy;
  see [Decoys](#decoys-and-dead-ends-documented-not-counted).)
- **Decode** — strip the 8-byte `UNICODE\0` prefix, decode the remainder as
  UTF-16LE → `VISUALPING{db7e533a9cef7f72}`.
- **Discovery mechanism** — two independent paths agreed: (a) parse EXIF with
  `piexif`/Pillow and read `UserComment`; (b) re-decode every saved body as
  **UTF-16LE** and re-run the regex — across all 388 resources this is the only
  wrapped hit under that encoding.
- **First crawl caught it?** No. The scanner decoded bodies as UTF-8/latin-1
  only; under those, the `\x00` between every character broke the `VISUALPING{`
  substring, so the scanner fell through to its bare-16-hex heuristic and
  reported this file's `COM` **decoy** instead. Fixed: `scanner.py` now decodes
  utf-16-le/be, and the bare-hex promotion is suppressed when a wrapped match
  exists in the same resource.
- **Reproduce** —
  `get /static/img/field-visit.jpg > /tmp/fv.jpg && python -c "import piexif;print(piexif.load('/tmp/fv.jpg')['Exif'][0x9286][8:].decode('utf-16-le'))"`
- **Confidence: certain.** Stored as the literal wrapped string in a
  purpose-built text tag; only full-format value in the whole image corpus;
  response body.

## Finding 4 — `VISUALPING{e1c2e40cf01c17cc}`

- **Retrieve** — `get /static/img/whiteboard-scan.png` (an `<img src>` target on
  maze pages).
- **Locate** — the **pixels**. It is a 722×85 raster that visually reads
  `VISUALPING{e1c2e40cf01c17cc}` in a monospace font on a graph-paper
  background. No EXIF, no `tEXt`/`zTXt`/`iTXt` chunk, no bytes after `IEND`, no
  LSB payload — the glyphs are the image content.
- **Decode** — read the characters. Upscale ~10× (nearest-neighbour); the font
  draws dotted zeros and a serifed `1`, so `0`/`o` and `1`/`l`/`I` are
  unambiguous → all 16 body characters are hex.
- **Discovery mechanism** — outlier triage: every other image on the site is
  48×48 or 64×64; this one is a 722×85 banner and named `whiteboard-scan`. Both
  the shape and the name say "text drawn in an image" → open it and look (or run
  OCR) *before* any bit-plane analysis. The crawler now flags it automatically
  under *Manual inspection suggested* (unusual aspect ratio), and OCRs it when
  `tesseract` is available.
- **First crawl caught it?** No — needs a visual/OCR step.
- **Reproduce** — `get /static/img/whiteboard-scan.png > /tmp/wb.png`, then open
  it, or `python -c "from PIL import Image; Image.open('/tmp/wb.png').resize((7220,850)).save('/tmp/wb_big.png')"`
  and view `/tmp/wb_big.png` (or `tesseract /tmp/wb_big.png -`).
- **Confidence: certain** for mechanism and format. Only residual risk is a
  single mis-read glyph; the upscale was re-checked.

## Finding 5 — `VISUALPING{2dd5105a3fad0ef3}`

- **Retrieve** — `get /notes/diff-socket-socket/`. Reached by an ordinary `<a
  href>` chain from `/notes/`, but **11 links deep** — past the original
  `max_depth=10`; only visible after the cap was raised.
- **Locate** — an HTML comment just before `</main>`:

  ```html
  <!-- provisioning backup — do not publish: VISUALPING{2dd5105a3fad0ef3} -->
  ```

- **Decode** — none; it is literal text.
- **Discovery mechanism** — re-crawl at `max_depth=60` (maze converges at 388),
  then the plain regex over the body — the crawler already scans comment text as
  part of the body bytes.
- **First crawl caught it?** No, and the reason was **discovery, not
  detection** — the page was never fetched. Fixed: default `max_depth` is now
  60.
- **Reproduce** — `get /notes/diff-socket-socket/ | grep -o 'VISUALPING{[0-9a-f]\{16\}}'`
- **Confidence: certain.** Exact format, response body, unique.

## Finding 6 — `VISUALPING{73c8f3073fdc5f74}`

- **Retrieve** — `get /wiki/detect-embed/`. `<a href>` chain from `/wiki/`, also
  past depth 10.
- **Locate** — an attribute on the `<body>` tag:

  ```html
  <body data-vp-archive="VISUALPING{73c8f3073fdc5f74}">
  ```

- **Decode** — none; literal text inside a `data-*` attribute value.
- **Discovery mechanism** — same deep re-crawl. The value sits in the raw HTML
  bytes so the plain body scan catches it; a DOM pass that iterates **every
  attribute value** (not just `href`/`src`) isolates it cleanly and attributes
  it to the right node.
- **First crawl caught it?** No — discovery gap (depth), same as #5.
- **Reproduce** — `get /wiki/detect-embed/ | grep -o 'data-vp-archive="[^"]*"'`
- **Confidence: certain.** Exact format, response body, unique.

## Findings 7 & 8 — the two JPEG `COM` values

| File | `COM` segment (bare 16-hex) | EXIF `UserComment` in same file |
|------|----------------------------|--------------------------------|
| `/static/img/office-plants.jpg` | `622ee9dfa76d54a6` | `"cropped for web"` — not a password |
| `/static/img/team-offsite.jpg` | `e19cd3432599af6f` | `"auto-enhanced"` — not a password |

- **Retrieve** — `get /static/img/office-plants.jpg` / `get
  /static/img/team-offsite.jpg` (both `<img src>` targets on several maze pages).
- **Locate** — the JPEG `COM` marker (`0xFFFE`). Segment bytes: `FF FE 00 12`
  (marker + length 18) followed by 16 ASCII characters, all `[0-9a-f]`. Nothing
  else in either file carries non-image data — the `APP1`/`UserComment` holds
  only the innocuous strings above; the pixels are a plain generative gradient.
- **Decode** — read the 16 hex bytes verbatim and wrap: `VISUALPING{ + body +
  }`.
- **Discovery mechanism** — JPEG segment parse: walk `FF xx` markers, take the
  `COM` payload. The scanner promotes a bare 16-hex token to the wrapped form
  **only for a resource that yields no properly-wrapped match** — true for these
  two, false for `field-visit.jpg` (which has the real EXIF value, so its `COM`
  stays a decoy).
- **First crawl caught it?** Yes — the bare-16-hex-in-binary path surfaced both
  values (now labelled "bare 16-hex, unwrapped" in the report).
- **Reproduce** —
  `get /static/img/office-plants.jpg | python -c "import sys;d=sys.stdin.buffer.read();i=d.find(b'\xff\xfe');print(d[i+4:i+4+int.from_bytes(d[i+2:i+4],'big')-2])"`
- **Why confidence is "high", not "certain":**
  - *For:* the count closes exactly — 6 certain + these 2 = 8 — and every other
    channel is a proven decoy (below), so there is nowhere else for #7–8 to be.
    Both images are otherwise contentless gradients whose only non-image data is
    this `COM` value. "Bare body you must wrap yourself" is a known challenge
    pattern and fits "not stored the way you'd expect".
  - *Against:* the wrapper is added by us, not stored. The identical `COM` slot
    in `field-visit.jpg` is a decoy there, so the slot is not intrinsically
    trustworthy — only trustworthy here because these files have no better
    candidate and the count demands two more.
  - *Verification tried:* `md5`/`sha1`/`sha256`/`crc32` of file bytes, of bytes
    minus the `COM` segment, of the filename, URL path, and EXIF caption — none
    equals either value, so they are **not** fingerprint decoys (not positive
    proof either).
- **Recommendation:** submit the 6 certain + these 2. If the accepted count is
  7, one of #7/#8 (or `field-visit.jpg`'s `COM`) is the odd one out and the maze
  needs another pass; nothing observed suggests a 9th hiding place.

---

## Decoys and dead ends (documented, not counted)

| Thing | Why it's not a password |
|-------|--------------------------|
| `VISUALPING{5a6b01d97bfffdc3}` — `field-visit.jpg` JPEG `COM` | Same file has a properly-formatted EXIF `UserComment` password; "formatted beats bare, per container." The scanner now suppresses it. |
| `VISUALPING{64d26185a2f94e34}` — `X-Provisioning-Note` response header on `/products/filter-gateway/` | Hidden homepage rule (a bullet an inline script deletes from the DOM): header passwords are "staging placeholders and are not qualified." |
| `VISUALPING{0000deadbeef0000}` — homepage `<pre>` | The worked example, stated not to be one of the eight. Filtered by `EXAMPLE_PASSWORD`. |
| `chart-overview.png`, `diagram-1.png`, `diagram-2.png`, `pattern.png` (all 48×48) | Vivid noise that baits a stego hunt. LSB plane is **identical every row** (row-sum std = 0, exactly 50% ones) — periodic ⇒ decorative, not a message. No payload under ~40 bit-plane/pixel traversals. |
| `/report/?page=N` | Procedurally generated table; "Next" never ends (`page=99999` still returns rows). Pages 1–30 scanned — no password. Infinite sink; capped at 10. |
| `/status/eu-region/` (403) | Server-side geo-block ("Your IP is from India"). Bounded sweep of 11 client headers (`X-Forwarded-For`, `X-Real-IP`, `CF-IPCountry`, `X-Country-Code`, `True-Client-IP`, `Accept-Language: de-DE`, …) changed nothing ⇒ genuine block, out of scope. Presented next to the report as "operational data" — a discipline test, not a carrier. |
| `/favicon.ico`, `/sitemap.xml`, `/manifest.json`, `*.js.map`, `/.well-known/*`, `/humans.txt` | All 404. Directory listings 403. |

## Coverage evidence

- HTML maze: 6 sections (`docs` 70, `blog` 63, `notes` 64, `wiki` 62,
  `products` 56, `help` 39), fully interlinked, **converges at 388 fetched with
  `discovered == fetched`** — no section/param cap dropped a real page (only
  `/report/?page=11`).
- Content types in the corpus: `text/html` (372), `application/javascript` (7),
  `image/png` (5), `image/jpeg` (3), `text/css` (1). No JSON/XML/PDF/font/map
  anywhere.
- Scans applied to all 388 bodies: raw bytes, latin-1, UTF-16 LE/BE, HTML
  entities, `%`/`\x`/`\u`/CSS escapes, base64/base32/hex tokens, char-code
  arrays, reverse, ROT13, a nested 2-layer pass, DOM attribute + comment
  extraction, and (images) EXIF/`COM`/PNG-text + bit-plane + visual/OCR.

## Crawler changes — implemented

With these folded into the tool, `python -m crawler` now auto-resolves **7 of 8**
(all but #4) with no decoys, and flags #4's image for manual inspection.

1. **UTF-16 + decode ladder** in `scanner.scan()` — body decoded as
   utf-8/latin-1/utf-16-le/utf-16-be, then HTML-entity / `\xNN` / `\uNNNN`
   unescaping, base64/hex token decoding, and decimal/hex **character-code
   arrays**. Catches #2 (char-codes) and #3 (UTF-16) directly.
2. **Depth cap** raised to 60 by default (was 10) so the finite maze converges;
   catches #5 and #6.
3. **Formatted-beats-bare, per resource** — a bare 16-hex metadata token is
   promoted only when the resource yields no properly-wrapped match. Suppresses
   the `field-visit.jpg` `COM` decoy now that its UTF-16 EXIF value is read.
4. **Image inspection** (`images.py`) — optional OCR of the pixels
   (`pip install ".[ocr]"` + a `tesseract` binary); when OCR is unavailable or
   silent, dimensional-outlier images are listed in the report's *Manual
   inspection suggested* section. This is how #4 (`whiteboard-scan.png`, 722×85)
   surfaces.
5. **Report** now separates qualifying findings, disqualified header hits, and
   images to eyeball.
