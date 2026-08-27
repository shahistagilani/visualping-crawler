# Crawler Best Practices — a universal reference

How to build a crawler that reliably **finds a thing** (a token, secret, pattern,
keyword, identifier) wherever it hides on a site — not just one that walks pages.
Written from first principles and hardened against real traps. Nothing here is
site-specific; the concrete examples at the end are illustrations, not rules.

> **Authorization first.** Only crawl origins and accounts you are permitted to.
> Keep an explicit origin allow-list, honor robots / rate-limits / `Retry-After`,
> never auto-submit state-changing forms, and never send credentials across
> origins. Page content must not be able to expand your scope.

---

## 0. The core model — two failure modes

A find-a-pattern crawler fails in exactly two ways:

1. **Discovery gap** — it never fetched the resource the target lives in.
2. **Detection gap** — it fetched the resource but didn't recognize the target
   inside it (wrong encoding, wrong container, only scanned visible text).

These have *unrelated* fixes, so when you come up short your **first** job is to
tell them apart — with data, not guesswork. That is what the coverage tally
(§1.4) is for: a content-type you expected but never fetched → discovery; a
content-type present with zero matches across all its rows → detection.

Two questions generate everything else. Ask them literally on every new site:

- **Q1 (discovery):** *If I were this site, what are all the ways a resource
  could be reachable?* — a reference in any attribute/CSS/JS/JSON, a URL computed
  at runtime, a convention (`sitemap.xml`, favicon, `.map`), a user action.
- **Q2 (detection):** *If I wanted this text present-but-unfindable to a naïve
  scan, yet still usable by the site, what could I do to it?* — different bytes
  (UTF-16), escapes, base64/hex, character-code lists, a different container
  (comment, attribute, image metadata, redirect hop, error body, or the pixels).

---

## 1. Universal engineering practices

### 1.1 Architecture

- **Stage the pipeline:** `fetch → canonicalize → extract links → scan for target
  → store`. Each stage independently testable and replaceable.
- **Dispatch on the real `Content-Type`** (with a bytes sniff fallback), never on
  the URL extension. `/foo` may be HTML, JSON, or a JPEG.
- **Persist every raw response body to disk**, keyed by canonical URL. This is
  the highest-leverage habit in the whole document: it turns "re-crawl the site
  to test a new idea" into "grep what I already have", and it is what makes the
  signature search (§4.6) possible.
- **Persist crawl state** (frontier, visited set, findings, per-URL log) after
  every item, so a crash or Ctrl-C is resumable and reruns are idempotent.
- **Keep provenance on every finding:** source URL, discovery path, the
  representation it was found in, a hash of the response. Results must be
  reproducible and a broken extractor must be auditable.

### 1.2 Fetching

- **Attach credentials at the session level** so *every* request carries them —
  pages, images, CSS, JS, redirect hops. A subresource request going out without
  auth and returning 401 is the most common silent hole. Re-check auth scope on
  cross-origin redirects; never follow one to a host outside the allow-list.
- **Always set connect + read timeouts.** No request may hang forever.
- **Bounded retries with exponential backoff + jitter**, on transient failures
  only (connection reset, timeout, 502/503/504). Never retry other 4xx. Honor
  `Retry-After` on 429/503.
- **Cap the response body size**; stream and abort past the limit. Log oversized
  skips — don't drop them silently.
- **Rate-limit**: low concurrency, a small inter-request delay, back off on
  errors. Set a descriptive `User-Agent`.
- **Handle redirects explicitly:** cap the chain length, record every hop, and
  **scan the intermediate responses and their headers** — a target can live on a
  hop.

### 1.3 Robustness

- **Isolate per-URL failures** in try/except; one bad page never aborts the crawl.
- **Decode with the declared charset *and* scan the raw bytes.** Never lose a
  match to a `UnicodeDecodeError`.
- **Resolve every extracted reference against the response's final URL**
  (post-redirect), with a real URL-join, after HTML-unescaping it.

### 1.4 Observability — the coverage tally

From run one, emit a **coverage summary**, not just a log:

- **by HTTP status** — a wall of 404/403 where you expected 200 is a
  discovery/auth problem;
- **by content-type** — a type you expected and don't see is discovery; a type
  present with zero matches everywhere is detection;
- **by section** (top-level path segment) — one section pinned at its cap while
  others are small means the cap is dropping real pages.

Plus a per-URL row: canonical URL, status, bytes, content-type, final URL, links
found, targets found, and what was capped/skipped and why.

---

## 2. Discovery — reach every resource and state (Q1)

### 2.1 Canonicalize *before* the visited check

The single biggest cause of loops is comparing raw URLs. Always reduce to a
canonical key first:

1. lowercase scheme + host; drop the default port;
2. resolve relative → absolute against the final URL;
3. drop the fragment (`#…`);
4. collapse dot-segments (`../`, `./`) and duplicate slashes;
5. normalize percent-encoding (uppercase hex, decode unreserved);
6. empty path → `/`;
7. fold `index.html` / `index.htm` / `default.aspx` ↔ the directory, and fold the
   trailing slash, so `/x`, `/x/`, `/x/index.html` are one key (confirm against
   the server's own redirect behavior);
8. **strip tracking/noise query params** (`utm_*`, `ref`, `fbclid`, `gclid`,
   `sid`, session ids, cache-busters); keep semantic ones (`page`, `id`, `q`);
9. sort the remaining params by key.

Keep the canonical key (for dedup) separate from the fetch URL (what you request).

### 2.2 The page is a resource graph, not a list of anchors

Following only `<a href>` is the #1 under-crawler. Extract from every carrier:

| Carrier | Where |
|---|---|
| HTML attributes | `a@href`, `link@href`, `script@src`, `img@src`/`@srcset`, `iframe@src`, `frame@src`, `form@action`, `area@href`, `object@data`, `embed@src`, `source@src`, `video/audio@src`, `track@src` |
| HTML misc | `<meta http-equiv=refresh>` URL, `style="…url(…)…"`, inline `<script>` / `<style>` bodies, **HTML comments** |
| CSS files | `url(…)`, `@import` |
| JS files | string literals that look like paths; route/menu tables; `fetch()` / `XHR` targets; `//# sourceMappingURL=` |
| JSON / XML | any string value that is URL-shaped; `sitemap.xml` entries |
| HTTP headers | `Location`, `Link`, `Content-Location`, `Refresh` |
| Conventions (seed even if unlinked) | `/sitemap.xml`, `/robots.txt`, `/favicon.ico`, `/manifest.json`, `/.well-known/*`, `*.map` |

Prefer a real HTML parser and a JS string-literal extractor over broad regexes.
Only enqueue in-scope URLs.

### 2.3 Converge the crawl; treat a firing cap as a warning

The goal is a crawl that **runs to natural convergence** — `discovered ==
fetched`, queue empty, within limits. Caps (§3) are a backstop against unbounded
generators, *not* a substitute for finishing. If a cap fires on a site that
turns out finite, assume it hid something: raise it (and the global max) and
re-crawl. A depth or count cap that trims real, browser-reachable pages is a
detection failure waiting to be blamed on the wrong thing.

### 2.4 Use a browser only when evidence demands it

If fetched pages are near-empty shells and routes are built by JS, drive a
headless browser: render, read the post-render DOM, and **capture the network
log** (XHR/fetch reveal API endpoints nothing links). Otherwise, parsing JS text
for path literals and route tables is cheaper and sufficient.

---

## 3. Loop, sink, and maze defense

Real sites contain structures that punish a naïve crawler. Survive them without
going blind.

- **Canonical visited set** (§2.1) — never fetch the same key twice.
- **Content-hash dedup** — hash the normalized body; a new URL that yields a
  seen hash is an alias: record it, don't re-extract links from it. Kills
  mirrored subtrees and many infinite spaces.
- **Two-level sink caps, by URL *shape* not exact URL:**
  - *per-template (fine)* — replace digits with a placeholder
    (`/report/?page=1..N` → `/report/?page=#`); cap per template. Bounds numeric
    pagination.
  - *per-section (coarse)* — group by top-level path segment; cap per section.
    Catches a **procedural maze** where every slug is unique (so per-template
    never fires) but a section swells with hundreds of never-repeating slugs.
- **Soft then hard cap** per signature: beyond the soft cap, divert to a
  low-priority queue (crawled last); beyond the hard cap, drop and **log the
  drop count** as completeness evidence.
- **Priority bypass for curated routes** — nav menus, JS route tables, sitemap
  entries are a small hand-authored set and exactly what a maze would starve;
  let them jump the queue and bypass caps. Keep the bypass scoped to genuinely
  curated sources.
- **Structural URL rejection** before enqueue: over-long URLs; a path segment
  repeating >2–3×; path depth beyond a bound; more than ~6 query params;
  parameters that only accrete each hop.
- **Soft-404 fingerprinting** — if the server returns 200 for nonsense paths,
  fingerprint a known-bad response and treat matches as dead ends.
- **Skip state-changing links** — `logout`, `delete`, `?action=`, `?vote=`.

---

## 4. Detection — recognize the target in every representation (Q2)

### 4.1 Scan raw bytes first

Never scan only a decoded-text convenience view — it guesses a charset, can
substitute characters, and mangles binary. Scan `response.content` as bytes,
then climb the ladder.

### 4.2 The representation ladder (cheapest first)

| Rung | What it defeats | How |
|---|---|---|
| raw bytes / latin-1 | nothing; baseline | substring / regex on bytes |
| **UTF-16 LE & BE** | two-bytes-per-char storage — a `\x00` between every letter. **The most common "present but invisible" cause.** | `data.decode("utf-16-le"/"be", "ignore")` then scan |
| entity / percent / CSS / JS unescape | `&#86;…`, `%56…`, `\56`, `\x56`, `V` | reverse each, then scan |
| base64 / base32 / hex tokens | a blob that decodes to the target | find bounded tokens, decode, scan the result |
| **character-code arrays** | `[86,73,83,…]`, `fromCharCode(86,73,…)`, space/comma/`0x` variants | join `chr(n)` for runs of ≥~10 numbers, then scan |
| reversed / ROT13 | late, situational | whole-string transform, then scan |
| nested (one extra layer) | double-encoding, e.g. base64 of a char-code string | re-run the ladder once on each decoded view |

Keep the target **pattern tight** (fixed prefix + exact body shape). A tight
pattern makes a false positive on transformed noise effectively impossible; a
loose one makes the whole ladder dangerous.

### 4.3 DOM-aware detection

- **Adjacent text-node concatenation** — reconstruct text across tags to catch a
  target split by markup (`VISU<span>ALPING{…}</span>`).
- **Every attribute value** — not just URL attributes; `data-*`, `title`, `alt`,
  `aria-*`, custom attributes on `<body>`.
- **Every comment** and every `<meta>` tag.

### 4.4 Beyond the response body

- **Response headers** (all of them, every request), **cookies**, **redirect-hop
  bodies**, and **non-2xx bodies** — a 403/404/500 page can carry the target.
- Note: a site may *declare* some channel out of scope (e.g. "values in headers
  are placeholders"). Honor stated rules — and read the page source, since such
  a rule may be present in markup a browser hides.

### 4.5 Images — open every channel

1. **Metadata:** EXIF tags including the Exif sub-IFD's **`UserComment`** (often
   UTF-16); JPEG **`COM`** markers; PNG **`tEXt` / `iTXt` / `zTXt`** chunks; run
   every field through the §4.2 ladder.
2. **Trailing bytes** after the JPEG `EOI` (`FF D9`) or PNG `IEND`.
3. **Bare body:** a metadata field whose *entire* value is the target's inner
   shape without its wrapper — treat as a candidate (see §5 for the decoy rule).
4. **Pixels / OCR — triage by outlier, then look:** if one image's **dimensions,
   aspect ratio, file size, or name** stand out from the rest (a wide banner
   among thumbnails; `whiteboard`, `scan`, `screenshot` in the name), the target
   is probably *drawn in it*. Upscale and read it; use OCR if needed. Check this
   *before* any bit-plane analysis — "in an image" usually just means "visible in
   the image".
5. **Bit-plane stego** only if the above are clean and there's a reason: extract
   each plane per channel, both bit orders, row- and column-major. A genuine
   hidden message has a high-entropy but *structureless* bit-plane; a decoy has a
   **periodic** low-bit stream (identical rows, a fixed `0xAA` pattern). Periodic
   ⇒ decorative ⇒ stop.

### 4.6 The signature search (the power move when stuck)

When you don't know *which* resource or *which* encoding: take the target's known
prefix, generate its form under **every** §4.2 transform, and grep the **saved
corpus** for all forms at once. A hit tells you the resource *and* the disguise
in one shot. A clean sweep is also informative — it rules out the entire text
corpus and points you at binary / metadata / pixels.

Make the harvester dedup and cap **exactly like the crawler** (strip tracking
params, cap numeric sinks) or it will "search everything" having fetched almost
nothing.

---

## 5. Decoys — recognize, probe briefly, move on

Content shaped like the target, placed to waste your time. Spend a **bounded**
probe, record a reasoned verdict, move on.

| Decoy | Tell / test |
|---|---|
| **Format look-alike** | Fails the exact rule (wrong length, prefix, alphabet). A tight regex rejects it automatically. |
| **Bare body vs formatted** | If the *same container* also yields a properly-wrapped target, a bare value alongside it is a decoy. Promote a bare value only when its container has nothing better. |
| **Fingerprint decoy** | A bare value that equals `md5`/`sha1`/`crc32` of the resource bytes, the filename, the URL, or a caption. Compute and compare. |
| **"Noise" image inviting stego** | Bit-plane is periodic / identical rows ⇒ decorative. (Real stego is structureless.) |
| **Infinite generator** (pagination, report table) | Rows are target-shaped but never valid; `?page=99999` still returns content; sample the first N pages then stop. |
| **Genuine vs bypassable block** | Try a small fixed set of client headers once (`X-Forwarded-For`, `X-Real-IP`, `CF-IPCountry`, `X-Country-Code`, `True-Client-IP`, `Accept-Language`). If nothing changes, it's a real server-side block — document it out of scope, don't escalate to proxies. |

When genuinely ambiguous, **surface it as a candidate with evidence** and let
final validation decide — don't silently include or exclude.

---

## 6. Completion criteria

Stop only on an **auditable** condition:

- the queue and permitted browser-state work are exhausted within limits **and
  the crawl converged** (`discovered == fetched`, no cap fired on a finite
  section); or
- a **known target count** is reached, with **every** finding strictly
  re-validated against the exact rule and a clean-state rerun reproducing the
  same set; or
- a time/safety budget is hit — and the report states what is unvisited and why.

If a count is known:

- it changes *when you stop* — it forces you past the easy finds;
- **"found N target-shaped fragments" ≠ "found the N targets."** Validate each.
- if you find **more than N** shaped values, some are decoys — identify *which*
  (§5), don't just take the first N;
- for each *missing* one, ask the reconciliation question: **"which category of
  resource have I fetched but not looked *inside* — with which representation?"**

---

## 7. Quick reference

### 7.1 Where targets hide (checklist)

- visible text · HTML comments · attributes (`data-*`, `title`, `alt`, custom)
- `<meta>` tags · response headers · cookies · redirect hops · non-2xx bodies
- CSS (comments, `content:`, custom properties) · JS (comments, string
  constants, **char-code arrays**, route tables)
- JSON / XML / SVG (`<text>`, `<metadata>`) · source maps
- base64 / hex / percent / entity / `\x` / `\u` encoded blobs — **including
  double-encoded**
- UTF-16 (or other non-default charset) storage
- image EXIF (`UserComment`, often UTF-16) · JPEG `COM` · PNG text chunks ·
  bytes after `EOI`/`IEND` · **pixels (rendered text)** · LSB stego
- pages that only exist past a naïve depth/pagination cap
- content behind a form POST or a client-side route change

### 7.2 "Stuck at found N of M" — decision tree

```
short on targets?
├─ coverage-by-status/type looks wrong (404 wall, a missing type)  → DISCOVERY
│    → enumerate referenced-but-unfetched resources; check non-<a> carriers;
│      seed well-known files; RAISE CAPS and re-crawl to convergence; try a browser
├─ a type is present but 0 matches in all its rows                 → DETECTION
│    → raw bytes → UTF-16 → adjacent-node text → unescape → base64/hex →
│      char-code arrays → nested; open header/redirect/error/metadata channels;
│      OCR outlier images
├─ don't know which resource or encoding                           → SIGNATURE SEARCH (§4.6)
└─ found ≥ M shaped values, unsure which are real                  → VALIDATE + decoy tests (§5)
```

### 7.3 Non-negotiables

- Auth on **every** request, including subresources and redirect hops.
- Canonicalize **before** the visited check.
- Scan **raw bytes**, and at least the UTF-16 + base64/hex + char-code rungs.
- Save **every** body to disk for offline re-analysis.
- Emit the **coverage tally** from run one.
- A firing cap on a finite site is a bug, not a success — raise it and re-crawl.
- Re-validate every finding against the exact target rule; reconcile to the
  known count; treat extras as decoys to be identified.

---

## Appendix — patterns seen in the wild

Concrete hiding spots from real crawls, as illustrations of the categories above.
A target of the form `PREFIX{<hex>}`:

| Representation | Example carrier | Rung / technique that catches it |
|---|---|---|
| Plain string literal | `var ADMIN_PASSWORD = 'PREFIX{…}'` in a JS file mimicking boilerplate | fetch every `<script src>`; regex on body |
| **Character-code array** | `var _beacon = [86, 73, 83, …]; String.fromCharCode(...)` | char-code-array rung of the ladder |
| **UTF-16 in image metadata** | JPEG EXIF `UserComment` = `UNICODE\0` + UTF-16LE `P\x00R\x00E\x00…` | decode bytes as utf-16-le before matching |
| **Rendered in pixels** | `whiteboard-scan.png`, a 722×85 banner among 48×48 icons | dimension/name outlier → upscale & read / OCR |
| HTML comment, deep in a maze | `<!-- do not publish: PREFIX{…} -->` 11 links from the seed | raise depth cap → crawl to convergence |
| Custom `data-` attribute | `<body data-vp-archive="PREFIX{…}">` | scan every attribute value, not just URL attrs |
| **Bare body in a JPEG `COM`** | `FF FE` segment whose whole payload is 16 hex chars, no wrapper | parse JPEG segments; promote bare body iff no wrapped match in that image |

Decoys from the same crawls: a full-format value in an `X-*` **response header**
that the site's own (DOM-hidden) rules declared out of scope; a JPEG `COM`
bare-hex in a file that *also* had a properly-formatted EXIF value (formatted
wins); four vivid PNGs whose **LSB plane was identical every row** (periodic ⇒
decorative); an infinitely paginated report table with target-shaped but
never-valid rows; a `/status/…` page behind a **genuine** server-side geo-block
that no spoofed header moved.
