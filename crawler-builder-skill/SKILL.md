---
name: crawler-builder
description: >-
  Design and build web crawlers that reliably FIND something on a site — a
  password, secret, token, keyword, ID, or any piece of content — no matter how
  it's hidden. Use this whenever the user is building, designing, debugging, or
  extending a crawler, scraper, spider, site-mapper, or content-extraction
  tool; whenever a crawler is "missing pages", "not finding" something it
  should, getting stuck in a loop, or drowning in junk URLs; and whenever the
  task is "crawl site X and find/extract Y". Reach for it even when the user
  just says "scrape", "spider", "walk the site", or "find all the ___ on this
  site" without naming a crawler. It explains, in plain language, where a target
  can hide, the disguises it can wear, how to avoid the site's traps, and how to
  work out what you're missing when you come up short.
---

# Crawler Builder

A plain-language guide to building a crawler whose job is to **find something** on a website. It works for any target you can describe with a pattern — a password like `SECRET{16 characters}`, an email address, an API key, a keyword. The examples below use `SECRET{...}` as a stand-in for whatever you're hunting.

You don't need a web-crawling background to use this. Every rule says what to do, why, and gives a small example.

> **Only crawl what you're allowed to.** Stick to the one website you've been given permission for. Never wander onto other websites it links to, and never send your login to a different website. This is good manners and a real safety rule — it stops a page from tricking your crawler into going somewhere it shouldn't.

## The one idea to hold onto

A crawler that's looking for something can only fail in **two ways**:

1. **It never downloaded the file the thing was in.** (a *finding* problem)
2. **It downloaded the file but didn't recognize the thing inside it.** (a *reading* problem)

These have completely different fixes. So the moment you come up short, your first job is to figure out **which of the two** you're dealing with — guessing wastes hours. The [running scoreboard](#keep-a-scoreboard) is what tells them apart in minutes.

The whole goal, in one line: **reach every file the site can give you, and read every disguise the thing might be wearing.**

## Two questions that generate everything else

You don't have to memorize a checklist. If you keep asking these two questions on any new site, you'll re-derive the right moves yourself — even ones no checklist mentions.

**Question 1 — "What are all the ways this site could hand me a file?"**
A file is reachable if *something points to it* (a link, an image tag, a stylesheet, a mention inside a script), if *the site's code builds the address on the fly* (a menu assembled by JavaScript, a redirect), if *a standard convention implies it* (a sitemap, a site icon), or if *a person's action reveals it* (a click, a form). Whenever you're missing pages, ask this and check each answer.

**Question 2 — "If I wanted to hide this text in plain sight, so an ordinary search misses it but the site can still use it, what would I do?"**
You'd store it in a different form: a different character encoding, an escape code, base64, a list of numbers, a comment, a hidden label, an image's info fields, or even painted into a picture. Whenever you *have* the file but can't find the thing, ask this and try each disguise.

The next two sections are just the written-out answers to these questions.

## Where the thing could be hiding

This is the heart of it. Two separate places to look, and you have to win both — did you **fetch** the right file, and did you **recognize** it once you had it?

### A. Files you might not think to download

- **The visible pages** — obviously.
- **Script and style files** the page loads (the `.js` and `.css` files). Plain text, easy to forget to open.
- **Images — the hidden text labels inside them**, not the picture. Photos carry info fields (camera details, captions, comments) that often hold exactly what you're after.
- **Error pages.** A "not found" or "forbidden" response still comes with a page body. Read it instead of throwing it away.
- **Redirect stops.** When one address bounces to another, the in-between response had a body too.
- **The response's labels** (called *headers*) — extra bits of info the server sends alongside the page.
- **Standard files nothing links to** — a sitemap, an app manifest, the little browser-tab icon. Try them anyway; sites usually have them.
- **Pages the site builds with its own code** — menus and links that only appear after the page's scripts run. A plain download sees an empty shell; you may need a real (headless) browser to see them.
- **The auto-generated filler pages.** Tempting to dismiss as junk — but the real thing is sometimes planted right inside them.

### B. Disguises the thing could be wearing

The *same* text can be stored so a plain search walks right past it. Undo these, easiest first:

- **Plain and visible** — sometimes it's just sitting there: in the text, in an HTML comment (`<!-- ... -->`), or in a hidden tag attribute. (Search the file's *exact* content, not a cleaned-up version — the clean version can quietly change characters or choke on images.)
- **Split by tags** — `ABC<span>DEF</span>` looks like one word to a person but two separate pieces to a naive search. Glue neighbouring pieces back together and search again.
- **A blank byte between every letter** — a real storage style (UTF-16) that turns `ABC` into `A·B·C·`. A normal search sees gibberish; you have to account for it. *This is the single most common "it's right there but invisible" case.*
- **Escaped** — web codes like `&#65;`, `%41`, or `\x41` that all just mean `A`.
- **Encoded** — packed as base64, or as hex, or as a **list of numbers where each number is one letter** (`[72,73]` = "HI").
- **Backwards, or shifted** — written in reverse, or every letter bumped along the alphabet by a fixed amount.
- **Stripped of its wrapper** — if the thing normally looks like `SECRET{....}`, you might find just the *inside* part, bare, sitting in a comment or a label. That still counts — don't dismiss it as the wrong shape. (One catch: if a single file holds *both* a fully-formed one *and* a bare one, the bare one is probably a decoy.)
- **Painted into a picture** — the text is *drawn* as pixels on an image (a banner, a screenshot, a photo of a whiteboard). No text search will ever find this; you have to **look at the image with your eyes**, or run image-to-text (OCR). Don't confuse this with the hidden text *labels* in point A — this is the picture itself.

Two ready-made helpers do the tedious parts for you: [`scripts/text_representations.py`](scripts/text_representations.py) tries all the disguises in section B on any text or file, and [`scripts/image_metadata.py`](scripts/image_metadata.py) reads the hidden text labels inside images. **Import and use them — don't rewrite them.**

## Traps to avoid (and how to spot them)

Real sites contain things designed to trip up or exhaust a crawler.

- **Endless numbered pages.** Some sections generate pages forever — `?page=1`, `?page=2`, `?page=3`… Notice when many addresses are identical except for a number, and cap how many you follow.
- **Auto-generated mazes.** Trickier: pages with unique made-up names, each linking to a dozen more unique made-up names, on and on. The "same shape" trick above won't catch it because every address looks brand new. Catch it a second way — notice when one *section* of the site is swelling with hundreds of never-repeating pages — and cap that too.
- **Cap gently before you cap hard.** When a section looks like a trap, first push the extra pages to the *back of the line* (crawl them only if you have spare time); only skip them outright past a higher limit. That way a genuinely large *real* section still gets covered.
- **Never let a trap hide a real page.** The hand-made pages (the menu, the sitemap entries) should always be crawled in full and jump the queue, even while you're capping the junk around them.
- **But remember the answer can be *in* the filler.** A cap keeps you from running forever, but it can also skip the very page you need. So when you know how many things there should be and you're short, *raise the caps and crawl further* — these mazes are usually finite even when they look endless.
- **Recognize bait and move on.** Some content is placed to waste your time: things shaped like your target but not quite it; a noisy image that looks like it hides a message but doesn't; a page that's genuinely locked (not just missing a header you could add). Give each a quick, bounded look, write down your reasoning, and move on.
- **Set hard ceilings.** Absolute limits on total pages, total time, file size, and depth. These are safety rails every crawler needs — loops and traps are normal, not rare.
- **Be polite.** Don't fire requests as fast as you can. Keep only a handful going at once, and slow down when the server says to ("too many requests").

## Keep a scoreboard

You can't fix a gap you can't see. From the very first run, keep a running tally: for every address, record what came back (worked / missing / forbidden), what kind of file it was, how big it was, how many links it produced, and whether you found anything. Then summarize it — totals by outcome, totals by file type.

This scoreboard is the most useful thing you'll build, because it instantly tells you *which of the two failures* you have:
- a wall of "not found", or a whole file type you never downloaded → a **finding** problem;
- a file type you *did* download but that produced zero results everywhere → a **reading** problem.

Also, for every thing you find, **write down where it came from** — the address, how you discovered it, and what disguise it was wearing. This lets you prove a result, repeat it, and catch a faulty reader that's inventing matches.

## When you're stuck

Being stuck is almost always a hidden assumption. Ask yourself, plainly:

- *What does a real browser fetch or run that my crawler doesn't?* (Menus/links built by scripts, background requests.)
- *What did the server hand me that I threw away unread?* (Headers. Redirect stops. Error pages. Images I only searched as text.)
- *What am I treating as junk without actually checking?* (A "noise" image, a "decoy" section, a "blocked" page — is it really empty, or did I just assume so? Open it and see.)
- *What disguise would slip past the exact search I'm running right now?* Then make sure it wouldn't.
- *Could the answer be inside the filler I'm skipping?*

**The one power move when truly stuck:** if you know even part of what you're hunting (say it starts with `SECRET`), don't hand-search page by page. Save every file you downloaded, then search that whole pile for that clue rendered in *every disguise at once* (backwards, as numbers, as base64, with blank bytes between letters, and so on). A hit tells you both *which file* and *which disguise* in a single step. A clean search is useful too — it rules out all the text files and points you at images or other odd files. (Details in [`references/diagnostics-playbook.md`](references/diagnostics-playbook.md).)

## Before you call it done

- **Double-check every result against the exact rule** and remove duplicates. Things that are *almost* the right shape are usually bait — but a value that's the right content just *missing its wrapper* (see disguises) is a real one, not bait.
- **If you know how many there should be, use that number.** It changes when you stop and forces you past the easy finds. And if you turn up *more* look-alikes than there should be, some are decoys — work out which (is the bare value just a fingerprint/hash of the file? is there a fully-formed one in the same place?), don't just grab the first few.
- **Prove it repeats.** Run the whole thing again from a clean start and confirm you get the same results.
- **Leave no silent holes.** If something is genuinely out of reach (a real lock, or text painted into a picture with no image-reading set up), say so plainly in the final report — the address, what you tried, why it's out of scope. "Found 7; the 8th is text drawn inside this image, value X, needs image-reading" is honest and useful. "Found 7" is not.

## How to build it (order that saves time)

Build the simplest version that could possibly work first, then add only what the scoreboard proves you need:

1. **Basic crawler** — stay on the allowed site, log in, follow ordinary links, search the raw file content, and print the scoreboard. Solves simple sites outright.
2. **Look everywhere** — follow every kind of link (section A), and try every disguise (section B). This is where most of the wins are.
3. **Handle the traps** — add the caps and priorities above so it can't loop or explode.
4. **Deepen only if needed** — read image labels; and add the two heavier tools *only when the scoreboard shows you must*: a real browser (if pages are near-empty and built by scripts) and image-to-text/OCR (if the thing is painted into a picture).
5. **Verify** — validate, check the count, prove it repeats.

## Where the details live

Keep this file for the *what and why*; open these for the *how*:

| File | Open it when |
|---|---|
| [`references/discovery.md`](references/discovery.md) | Building the "follow every kind of link" part, or missing pages. |
| [`references/inspection-and-decoding.md`](references/inspection-and-decoding.md) | Building the "try every disguise" part, or the thing is there but unseen. |
| [`references/decoys-and-pitfalls.md`](references/decoys-and-pitfalls.md) | The crawl loops, explodes, drowns in junk, or you suspect bait. |
| [`references/diagnostics-playbook.md`](references/diagnostics-playbook.md) | Stuck at "found N of M" and need to work out what's missing. |
| [`scripts/text_representations.py`](scripts/text_representations.py) | You need the disguise-undoing done for you. Import it. |
| [`scripts/image_metadata.py`](scripts/image_metadata.py) | The thing might be in an image's hidden text labels. Import it. |

The reference files carry more precise, technical detail (exact tag names, status codes, tuning numbers). That's on purpose — this page stays plain so anyone can follow it; the depth is one click away when you're ready to write the code.
