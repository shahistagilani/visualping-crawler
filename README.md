# Visualping Crawler Challenge

An authenticated web crawler that starts at a configured homepage, walks every
page and resource a real browser could reach, and scans all of it for the eight
hidden passwords of the form `VISUALPING{<16 lowercase hex>}`.

The problem analysis lives in [`challenge.md`](challenge.md); the design
principles the crawler follows are in
[`crawler-best-practices.md`](crawler-best-practices.md); the located passwords
and how each was verified are in [`findings.md`](findings.md).

---

## Setup

```bash
# 1. environment + install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"          # or: pip install -r requirements.txt

# 2. configuration — copy the template and fill in real values
cp crawler.example.toml crawler.toml
$EDITOR crawler.toml
```

`crawler.toml` holds the target URL and credentials. It is **git-ignored** so
secrets are never committed; `crawler.example.toml` is the checked-in template:

```toml
[target]
base_url = "https://example.com/"   # also fixes the crawl's host scope

[auth]
username = "your-username"          # HTTP Basic Auth, sent on every request
password = "your-password"
```

Any value can instead be supplied by an **environment variable**
(`CRAWLER_BASE_URL`, `CRAWLER_USER`, `CRAWLER_PASS`) or a **CLI flag**
(`--base-url`, `--username`, `--password`). Precedence: flag → env var → file.

---

## Running the crawler

```bash
python -m crawler                       # uses ./crawler.toml, writes ./output/
python -m crawler --output run1         # choose the output directory
python -m crawler --config other.toml   # use a different config file
cat output/report.md                    # read the results
```

The crawl prints a live line per fetch and, at the end, a summary table of
qualifying findings. Full results are written to the output directory (see
[Output](#output)).

Run without a config file (secrets stay out of shell history via env vars):

```bash
CRAWLER_BASE_URL=https://example.com/ CRAWLER_USER=me CRAWLER_PASS=secret \
  python -m crawler
```

### Options

| Option | Default | Purpose |
|--------|---------|---------|
| `--config PATH` | `./crawler.toml` | TOML config file with target + auth. |
| `--base-url URL` | from config | Seed URL; also fixes the crawl's host scope. |
| `--username USER` | from config | HTTP Basic Auth user. |
| `--password PASS` | from config | HTTP Basic Auth password. |
| `--output DIR` | `output` | Directory for raw pages and reports. |
| `--max-fetches N` | `2000` | Hard ceiling on requests made. |
| `--max-depth N` | `60` | Maximum link depth from the seed. |
| `--delay SECONDS` | `0.25` | Politeness pause between requests. |

Credentials are sent on **every** request, including static assets and redirect
hops.

---

## How it works

A breadth-first walk from the seed. For each URL the frontier hands back:

1. **Fetch** it with auth, timeouts, bounded retries, and a response-size cap
   (`http.py`).
2. **Scan** the response for the target across representations (`scanner.py`):
   the body as UTF-8 / latin-1 / **UTF-16 LE+BE**, HTML entities and
   `\xNN`/`\uNNNN` escapes, base64 / hex tokens, **decimal character-code
   arrays**, response headers (recorded but *disqualified*), and — for binary
   resources with no wrapped match — a bare 16-hex token in metadata.
3. **Inspect images** (`images.py`): OCR the pixels when `pytesseract` +
   `tesseract` are available; otherwise flag dimensional-outlier images (a wide
   banner among icons) for manual review.
4. **Store** the raw body to `<output>/pages/` so re-analysis never needs a
   re-crawl (`storage.py`).
5. **Skip expansion** if this exact body was already seen (content-hash dedup).
6. **Extract links** — not just `<a href>`, but `<link>/<script>/<img>/<iframe>/
   <form>/…`, inline CSS/JS, HTML comments, standalone `.css`/`.js` files, and
   quoted path literals inside JavaScript (`extract.py`).
7. **Canonicalise** each link and enqueue it if in-scope and no guard trips
   (`urlnorm.py`, `frontier.py`).

### Loop / spider-trap defences

- Canonical URLs only in the visited set: `/x`, `/x/`, `/x/index.html`,
  `/x/?utm_source=…` all collapse to one key.
- Content-hash dedup for mirrored subtrees.
- Hard budgets: max fetches, depth, frontier size, body size, wall-clock.
- URL-shape rejection: over-long URLs, deep paths, repeated path segments,
  parameter accretion.
- **Per-`(path, param)` value cap** — after N distinct values of e.g. `page`,
  new ones stop being enqueued. This is what bounds an infinite `?page=N` table.

Full ruleset and rationale: [`crawler-best-practices.md`](crawler-best-practices.md).

---

## Output

Written under `--output` (default `output/`):

| Path | Contents |
|------|----------|
| `report.md` | Human-readable summary: qualifying findings with source + location, disqualified header hits, images flagged for manual inspection, loop-guard rejection counts, failed fetches. |
| `report.json` | Machine-readable: stats, deduped value list, every finding, full crawl log. |
| `pages/` | Raw response body of every fetched URL, named `<path>.<hash><ext>`. |

Output directories and `crawler.toml` are git-ignored.

---

## Project layout

```
visualping-crawler/
├── README.md                     you are here
├── challenge.md                  problem breakdown + recon findings
├── crawler-best-practices.md     universal crawler reference (hygiene, discovery,
│                                 detection ladder, sink/decoy handling)
├── findings.md                   the located passwords + verification evidence
├── crawler.example.toml          config template (copy to crawler.toml)
├── pyproject.toml                package metadata, deps, pytest config
├── requirements.txt              plain dependency list
│
├── src/crawler/
│   ├── __main__.py               CLI entry point (`python -m crawler`)
│   ├── config.py                 Settings loader (file/env/flag) + Limits dataclass
│   ├── urlnorm.py                canonicalisation, scope check, trap-shape check
│   ├── http.py                   Fetcher: auth, retries, timeouts, size cap
│   ├── extract.py                link discovery from HTML / CSS / JS / comments
│   ├── scanner.py                target detection across the representation ladder
│   ├── images.py                 optional image OCR + outlier flagging
│   ├── frontier.py               queue + dedup + depth/param/trap guards
│   ├── storage.py                persist raw bodies and JSON
│   ├── report.py                 render report.md / report.json
│   └── crawler.py                orchestrator wiring it all together
│
└── tests/
    ├── test_urlnorm.py           canonicalisation, scope, trap shapes
    ├── test_extract.py           link extraction across element/asset types
    ├── test_scanner.py           representation ladder, header disqualification, bare-hex suppression
    ├── test_frontier.py          dedup, depth cap, per-param value cap, FIFO
    ├── test_http.py              retries, timeouts, body cap (fake session, no network)
    └── test_crawler.py           end-to-end crawl over an in-memory fake site
```

---

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

All tests are offline — `test_http.py` and `test_crawler.py` use fake
sessions/fetchers, so the suite never touches the network and needs no
`crawler.toml`.

---

## Coverage and limitations

Against the challenge site the crawler auto-resolves **7 of the 8** passwords
(plain text, HTML comment, `data-*` attribute, JS string literal, JS
character-code array, UTF-16 EXIF `UserComment`, and two bare-hex JPEG `COM`
segments). The 8th is drawn into `whiteboard-scan.png`'s pixels; with
`pip install ".[ocr]"` **and** a `tesseract` binary on PATH the crawler OCRs it
too — otherwise it lists that image under "Manual inspection suggested".
`findings.md` has the full evidence for all eight.

- **JavaScript is parsed, not executed.** Link discovery reads path literals out
  of script text rather than running a headless browser. A JS-heavy target would
  need a rendering pass.
- **OCR is best-effort and off by default** — it needs the optional
  `pytesseract` package and a system `tesseract` install.
- **No deep steganography.** Bit-plane / LSB payloads are not extracted (the
  decoy noise images on this site have none).
- **Geofenced / IP-blocked content** is logged as an unresolved item, not
  bypassed.
