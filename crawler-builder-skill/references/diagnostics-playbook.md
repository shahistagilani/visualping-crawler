# Stuck-Crawl Diagnostic Playbook

Use this when the crawl runs clean but you're **short** — "found N of M", or "still not finding" something. Cardinal rule: **localize the failure to discovery or detection before changing anything.** Guessing burns hours; the coverage data answers it in minutes.

## Step 1 — Read the coverage summary, not the log

You built the coverage summary in Phase 1 (if not, build it now — highest-leverage hour you'll spend). Look at:
- **Coverage by status:** a wall of 404s, or 403s where you expected 200s → **discovery/auth** problem.
- **Coverage by content-type:** a type you expected (images, JSON, JS) **absent** → discovery gap (never linked/followed). A type **present with zero matches across all its rows** → **detection** gap (fetched but unreadable).
- **Per-section volume:** one section pinned at its cap while others are small → the cap may be **dropping real pages**; raise it.

This single read usually tells you which half you have. Everything below branches on it.

## Step 2A — If it's a discovery gap

1. **Enumerate the resource inventory.** Grep the corpus for `src=`/`href=`/`url(` — list every distinct non-HTML resource referenced anywhere (JS, CSS, images, JSON, fonts, maps). Did you fetch each? A referenced-but-never-fetched resource is a missed carrier.
2. **Diff against a fuller crawl.** Temporarily raise the caps and `max_visited` and re-run. If the found-count jumps, the caps were the problem — targets were seeded in capped pages. If it stays flat, discovery is fine and the gap is detection.
3. **Check the non-clickable-link places:** `img`/`iframe`/`form`/`srcset`/CSS-`url()`/source-maps. A page reachable only via one of these is invisible to a crawler that follows only ordinary links.
4. **Check well-known files** (`sitemap.xml`, manifest, favicon) and **JS route tables**.
5. **Consider the browser.** SPA + static-only → routes may exist only after JS runs.

## Step 2B — If it's a detection gap

You have the file; you're not seeing the target. Work through the disguises:
1. **Scan raw bytes, then utf-16.** If you were on a decoded-text view, switch to bytes + latin-1 + **utf-16** (LE/BE). UTF-16 is the most common "present but invisible" cause.
2. **Reconstruct parsed text** (adjacent text-node concatenation) for markup-split targets.
3. **Open the metadata channels** — image EXIF/`COM`/PNG-text (`scripts/image_metadata.py`), headers, redirect bodies, error-page bodies.
4. **Climb the decode ladder** — entities, escapes, base64/hex, char-code arrays (`scripts/text_representations.py`).
5. **Accept an unwrapped body** — a metadata/comment field that is exactly the inner shape.
6. **Consider pixels/OCR** — if the resource is an image and metadata is clean, the target may be *drawn* in it.

## Step 3 — The signature search (the power move when you're truly stuck)

When you don't know *which* representation or *which* resource hides the target, don't scan blindly — **search the whole corpus for the target's known prefix in every encoding at once.** A hit tells you the resource **and** the encoding.

Harvest every response body to disk (respecting scope/limits), then for a known prefix generate its form under each transform and grep the corpus for each:
- decimal char-codes (`65,66,67,...` and concatenated), hex (`414243...`, `\x41...`, spaced);
- `A...`;
- base64 prefix, base32, ascii85, base85;
- reversed, ROT13;
- HTML entities (`&#65;...`);
- binary (`01000001...`);
- **utf-16** (`A\x00B\x00C\x00...`).

A clean sweep is itself informative — it rules out the entire text corpus and points you at binary/metadata/pixels.

**Watch the harvest's own dedup.** A harvester that dedups on the raw URL will drown in `?ref=`/`?page=` variants and abort before covering the site — strip tracking params and cap numeric sinks in the harvester exactly as the crawler does, or you'll "search everything" while having fetched almost nothing real.

## Step 4 — Cross-check against a known count

If you know the count, the gap between found and expected is your worklist. Treat **near-misses and decoys as unresolved, not answers** — validate each candidate strictly. A common outcome: you find *more* than N shaped values and must identify the decoy(s) — the bare-vs-formatted and hash tests in `decoys-and-pitfalls.md` resolve most of these. "Found N target-shaped things" is not "found the N targets" until each passes the strict rule.

## Step 5 — Make the gap auditable

If a target is genuinely out of reach (real geo-block, pixel-only image with no OCR budget), **document it** — the URL, what you tried, why it's out of scope — rather than a silent hole. "7 auto-found; 1 documented in an image's pixels, value X, needs OCR" is honest and reproducible; "found 7" is neither.

## Quick decision tree

```
short on targets?
├─ coverage-by-status/type looks wrong (404 wall, missing type)  → DISCOVERY  → Step 2A
├─ type present, 0 matches in all its rows                       → DETECTION  → Step 2B
├─ don't know which resource/encoding                            → SIGNATURE SEARCH → Step 3
└─ found ≥ N shaped values, unsure which are real                → VALIDATE + decoy tests → Step 4
```
