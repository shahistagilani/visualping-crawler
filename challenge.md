# VisualPing Crawler Challenge

## The Goal

Build an authenticated web crawler that starts at the target homepage, walks the
entire site the way a browser would, fetches **every** resource it references
(not just HTML pages), and scans all of it for **8** passwords matching:

```
VISUALPING{[0-9a-f]{16}}
```

Example (not one of the eight): `VISUALPING{0000deadbeef0000}`

### Target and credentials

Not stored in this repo. The site URL and HTTP Basic Auth credentials live in
`crawler.toml` (git-ignored; copy `crawler.example.toml`) or the
`CRAWLER_BASE_URL` / `CRAWLER_USER` / `CRAWLER_PASS` environment variables. See
[`README.md`](README.md#setup). Credentials are sent on every request.

## What the ask actually is

Crawl from the homepage, following references, and extract 8 hidden passwords.

Two hard constraints:

- **Basic Auth on every single request** — including images, CSS, JS, favicon,
  everything. Miss the header on an asset request and you get a 401 instead of
  the file that hides a password.
- **No guessing** — you never invent URLs. Everything is reachable by following
  references from pages you've already fetched. No hidden URLs, no wordlists, no
  robots.txt tricks. If you can't find a password, your crawler isn't extracting
  some kind of reference, or isn't inspecting some kind of resource.

## Why it's not trivial (decoding the hints)

### Hint 1 — "not everything a browser sees is an `<a>` tag in the HTML source."

Link discovery has to go far beyond `<a href>`. References live in:

- Other HTML elements: `<link>`, `<script src>`, `<img src>`, `<iframe>`,
  `<form action>`, `<source srcset>`, `<object>`, `<embed>`, `<video>`/`<audio>`,
  `<area>`, `<meta http-equiv="refresh">`
- Attributes that aren't URLs by default: `data-*`, `style="background:url(...)"`
- Inside CSS files: `url(...)`, `@import`
- Inside JS files: string literals that are paths / endpoint names, `fetch()`
  targets
- HTTP response headers: `Location` (redirects), `Link:`, `Content-Location`,
  `Set-Cookie`
- Standard side-channel files: `robots.txt`, `sitemap.xml`, `humans.txt`,
  `/.well-known/`
- Content rendered only after JavaScript runs — which a plain HTTP-plus-regex
  crawler never sees. This likely means a **real headless browser**
  (Playwright/Puppeteer) is needed for at least some pages, and the browser's
  **network log** should be captured (XHR/fetch calls reveal API endpoints).

### Hint 2 — "passwords are not always in the visible text… not always stored the way you'd first expect."

For each response, scan *everything*, not just rendered text:

- HTML comments, `meta` tags, attribute values (`alt`, `title`, `aria-*`)
- Raw HTTP response headers and cookies
- CSS comments and `content:` values
- JS comments and constants
- JSON / API response bodies (scan recursively)
- Base64 blobs / `data:` URIs (decode, then scan)

### Hint 3 — "pages reference other kinds of resources too; some passwords live in those."

Non-HTML resources need type-specific inspection:

- **Images**: EXIF/XMP metadata, PNG `tEXt`/`iTXt` chunks, comment fields,
  possibly text drawn into the pixels or simple steganography.
  Tools: `exiftool`, `strings`, `zsteg`/`binwalk`.
- **PDFs**: extract text *and* document metadata (`pdftotext`, `exiftool`).
- **SVG**: `<text>` elements, `<metadata>`, comments.
- **Downloadable files**: `.txt`, `.csv`, `.zip`/`.tar` (extract, then scan
  contents), `.bak`, source maps (`.js.map`).
- **Favicon, fonts** — still fetch and scan.

## The crawler design (conceptual)

1. **Frontier + visited set.** Queue of URLs to fetch; normalized (resolve
   relative → absolute, strip fragments, canonicalize trailing slash/case) so it
   doesn't loop. Scope strictly to host `54.214.7.161`.
2. **Fetcher.** Every request carries the `Authorization: Basic` header. Record
   status, all headers, content-type, and the raw body bytes for each response.
   Follow redirects but inspect the intermediate responses too.
3. **Extractor, dispatched by content-type:**
   - `text/html` → parse DOM for every reference type listed above, plus inline
     `<script>`/`<style>` blobs, plus comments.
   - `text/css` → `url()` / `@import`.
   - `*/javascript` → candidate path strings.
   - `application/json` / `xml` → recurse for URL-like strings; parse
     `sitemap.xml`.
   - anything else → treat as a leaf resource (no link extraction, but still
     scanned).
4. **Password scanner.** Run the regex `VISUALPING\{[0-9a-f]{16}\}` against: the
   response body (as text and as raw bytes), all header values, cookie values,
   and — for binary types — the output of the resource-specific extraction step
   (exiftool dump, pdftotext, unzip listing, etc.). Log **URL + location** for
   every hit.
5. **JS-rendering pass.** For HTML pages, also load them in a headless browser,
   wait for network idle, then (a) re-extract links from the post-render DOM and
   (b) add every URL the browser requested to the frontier. This catches SPA
   routes and API calls.
6. **Aggregate.** Dedupe hits. Expect exactly 8 distinct passwords. Keep a table
   of `password → where found` to prove completeness and spot if only 6–7 turned
   up (meaning a resource type is still unexamined).

## Practical order of work

1. **Manual recon first** (before writing code): fetch the homepage with curl,
   read the raw HTML, headers, cookies; grab `robots.txt` and `sitemap.xml`;
   open it in a headless browser and watch the network tab. This tells you
   whether the site is static or JS-driven, and what resource types are in play
   — which shapes the crawler.
2. Build the HTTP crawler with the multi-source extractor and the scan-everything
   scanner. Get the "easy" passwords (visible text, comments, headers,
   robots.txt, a JS/CSS file).
3. Add resource inspection (exiftool/pdftotext/unzip) for the binary hits.
4. Add the headless-browser rendering + network-capture pass for anything the
   static crawler can't reach.
5. Reconcile to 8. For each missing one, ask "what category of thing have I
   fetched but not looked *inside*?"

## Where passwords could hide (checklist)

- Visible HTML page text
- HTML comments
- HTML attributes (`title`, `alt`, `data-*`, `aria-*`)
- `meta` tags
- HTTP response headers (custom `X-` headers)
- Cookies (`Set-Cookie`)
- `robots.txt` / `sitemap.xml` / `humans.txt` / `security.txt`
- CSS files (comments, `content:` property)
- JS files (comments, string constants)
- JSON / API responses
- Image EXIF / XMP / PNG text chunks / rendered pixels / steganography
- PDF body text or document metadata
- Favicon / fonts
- Redirect chains (intermediate responses)
- 404 / error pages
- Downloadable files (`.txt`, `.zip`, `.csv`, `.bak`, `.js.map`)
- SVG `<text>` / `<metadata>` / comments
- Base64-encoded blobs / `data:` URIs (decode first)
- `/.well-known/`

## Recon findings (2026-08-27)

Static `nginx/1.30.4` site. Basic Auth required on every path (assets included).
`robots.txt` and `sitemap.xml` both 404.

### Extra rule discovered on the homepage

The homepage rules list contains a 4th bullet **that an inline `<script>` deletes
from the DOM** — so a browser user never sees it, but the HTML source does:

> "Passwords that appear in HTTP response headers are staging placeholders and
> are not qualified — ignore them."

So: still read headers during the crawl, but header hits do **not** count toward
the 8. (This is itself an example of "not everything the browser shows matches
the source.")

### Site map

| Path | Notes |
|------|-------|
| `/` | Rules page. Links to the 6 sections + `/report/?page=1` + `/status/eu-region/`. |
| `/static/css/style.css` | Plain CSS, no secret. |
| `/static/js/main.js` | **Real.** Injects 7 nav links into `[data-extra-nav]` — these paths appear in **no `<a>` tag** anywhere. This is the "not every link is an `<a>`" mechanism. |
| `/static/js/widgets.js`, `telemetry.js`, `carousel.js` | Near-identical boilerplate **decoys**. No injected links. Loaded from a few wiki pages. |
| `/docs/ /blog/ /products/ /help/ /notes/ /wiki/` | Section indexes. Filler "word-salad" text. Each links to deeper `related` / `see also` pages. |
| deep pages e.g. `/docs/<slug>/`, `/wiki/<slug>/`, `/blog/<slug>`, `/products/<slug>/` | Recursive graph of interlinked filler pages. Full recursive crawl needed. Some carry `<figure><img>`. |
| `/static/img/*` | `field-visit.jpg`, `office-plants.jpg`, `pattern.png`, `diagram-2.png` (referenced from figures). |
| `/report/?page=N` | Procedurally generated table. "Next" link **never ends** (`page=99999` still returns rows). **Infinite-pagination trap** — needs a crawl cap / loop guard. `debug=1` param does nothing. |
| `/status/eu-region/` | **403 geofence**: "only visible to Germany region. Your IP is from India." Not bypassed by `X-Forwarded-For`, `Accept-Language: de-DE`, or `CF-IPCountry: DE`. Open puzzle — likely 1 password behind it. |

### The 7 JS-injected paths (from `main.js`, not in any `<a>`)

```
/docs/upstream-sample-channel/     /notes/archive-region/
/wiki/shard-schedule/              /docs/change-signal-anchor/
/wiki/rule-change/                 /wiki/digest-session-ledger/
/wiki/domain-queue-backoff/
```

### URL-normalization requirement (observed)

The same page is linked many ways — `/blog`, `/blog/`, `/blog/index.html`,
`/blog/?utm_source=internal`, `/wiki/?v=7`, `/products/?hl=en`, `/help/?ref=nav`.
Canonicalize: resolve relative, drop fragment, fold `index.html` ↔ `/`, strip
tracking params (`utm_source`, `v`, `hl`, `ref`, `utm_*`) so all variants collapse
to one visited key.

### Passwords located — 8 of 8 (see `findings.md` for full evidence)

6 certain + 2 high-confidence-by-elimination. Found after (a) re-crawling the
maze to convergence at depth 60 (388 resources), and (b) running the full
`crawler-builder` decode ladder + image/OCR inspection offline.

| # | Password | Source | Mechanism | Conf. |
|---|----------|--------|-----------|-------|
| 1 | `VISUALPING{349a583fba34c301}` | `/static/js/analytics.js` | JS string literal `ADMIN_PASSWORD` | certain |
| 2 | `VISUALPING{fb725e1f3d6728b1}` | `/static/js/theme-switcher.js` | char-code array `_beacon=[86,73,…]` | certain |
| 3 | `VISUALPING{db7e533a9cef7f72}` | `/static/img/field-visit.jpg` | EXIF `UserComment`, UTF-16LE | certain |
| 4 | `VISUALPING{e1c2e40cf01c17cc}` | `/static/img/whiteboard-scan.png` | drawn in pixels (OCR) | certain |
| 5 | `VISUALPING{2dd5105a3fad0ef3}` | `/notes/diff-socket-socket/` | HTML comment (depth 11) | certain |
| 6 | `VISUALPING{73c8f3073fdc5f74}` | `/wiki/detect-embed/` | `data-vp-archive` attr on `<body>` (depth 11) | certain |
| 7 | `VISUALPING{622ee9dfa76d54a6}` | `/static/img/office-plants.jpg` | JPEG `COM` segment, bare hex → wrapped | high |
| 8 | `VISUALPING{e19cd3432599af6f}` | `/static/img/team-offsite.jpg` | JPEG `COM` segment, bare hex → wrapped | high |

**Decoys (documented, not counted):** `5a6b01d97bfffdc3` (field-visit.jpg `COM`,
superseded by its EXIF value); `64d26185a2f94e34` (`X-Provisioning-Note` header —
disqualified by rule); `0000deadbeef0000` (homepage example); the 4 noise PNGs
`chart-overview`/`diagram-1`/`diagram-2`/`pattern` (periodic per-row LSB);
`/report/?page=N` (infinite sink); `/status/eu-region/` (genuine geo-block).

### Tooling gap

`exiftool`, `pdftotext`, `binwalk`, `zsteg` are **not installed**. Options:
`brew install exiftool poppler binwalk`, or parse EXIF / PNG chunks in Python
(`Pillow` / `piexif` / manual chunk walk).

### Status: all 8 located (findings 7 & 8 pending a submission check)

Remaining verification: submit findings 1–6 (certain) + 7–8 (`office-plants.jpg`
/ `team-offsite.jpg` `COM` values). If the accepted count is 7 rather than 8,
one of the `COM` values is a decoy and the maze needs another pass — but no 9th
hiding place has surfaced across a converged crawl + full decode ladder + image
analysis.

### Crawler changes implied by the hunt (see `findings.md` §"Crawler changes")

- Add a UTF-16 LE/BE decode pass to `scanner.scan()` (would have caught #3).
- Add the decode ladder — char-code arrays + base64/hex tokens (would have caught #2).
- Raise / replace the depth-10 cap with a per-section soft/hard cap (would have caught #5, #6).
- Parse image EXIF/`COM`/PNG-text explicitly and label hits; add an OCR/visual
  step for images whose shape or name implies rendered text (would have caught #4).
- Tier the report: full-format body hits vs bare values promoted from metadata.

## Main gotchas to plan for

- Forgetting auth on asset requests → silent 401s that look like empty
  resources.
- URL normalization / infinite spaces (query-param variations) → cap crawl size
  and dedupe aggressively.
- Same password appearing in multiple places → dedupe by value, not by location.
- A password that's split, encoded (base64/hex/rot13), or embedded in binary
  metadata rather than sitting in plain text.
- Assuming static HTML is the whole site when key pages/links only exist after
  JS runs.
- Rate limiting — be polite, add small delays if the server pushes back.
