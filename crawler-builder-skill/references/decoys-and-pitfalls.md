# Sinks, Mazes, and Decoys

Real sites contain structures that punish a naïve crawler: infinite pagers, procedurally-generated link mazes, and content shaped to waste your time. A thorough crawler must **survive** these without going blind to real content. First principle: anything that grows without bound, or is shaped like the target but isn't, is an *adversarial structure* — learn to recognize the pattern of adversariality, not just the specific traps below.

## Table of contents
- [Two-level sink capping](#two-level-sink-capping)
- [Priority seeding so caps don't blind you](#priority-seeding-so-caps-dont-blind-you)
- [Soft vs hard caps](#soft-vs-hard-caps)
- [The target can be in the filler](#the-target-can-be-in-the-filler)
- [Recognizing decoys](#recognizing-decoys)
- [The bare-vs-formatted ambiguity](#the-bare-vs-formatted-ambiguity)
- [Genuine blocks vs bypassable ones](#genuine-blocks-vs-bypassable-ones)
- [Tuning defaults](#tuning-defaults)

## Two-level sink capping

Reduce each URL to shape signatures and cap by shape, not exact URL. Two levels catch different traps:

**1. Per-template (fine).** Replace numeric path segments and numeric query values with a placeholder: `/report/?page=1..N` → template `/report/?page=#`. Cap URLs per template. This bounds a numeric pagination sink to a handful of fetches — the template cap is what keeps an unbounded pager from eating the crawl.

**2. Per-section (coarse).** Group by top-level path segment (`/docs/`, `/wiki/`). This catches what per-template structurally **cannot**: a **procedural maze** where every URL is textually unique (`/docs/blue-fox-lamp` → `/docs/green-owl-desk` → a dozen more, forever). Each URL is its own template with count 1, so the per-template signal never fires — but a *section* accumulating hundreds of never-repeating slugs **is** the signature. Cap per section too.

Expose the counts as diagnostics: "top sections by volume" and "distinct templates per section." A section whose URL-count ≈ its distinct-template count is a maze; many URLs across few templates is ordinary pagination.

## Priority seeding so caps don't blind you

Caps risk dropping **real, curated** pages that happen to live in a maze section. Defense: routes from a curated source — a nav menu, a JS route table, a sitemap — are a small hand-authored set and are exactly the pages a maze would otherwise starve. Mark them **priority** and let them **bypass the section/template caps**, jumping the queue. Keep the bypass scoped to genuinely curated sources — don't bypass caps for arbitrary JS string literals, or you've removed the protection.

## Soft vs hard caps

Two thresholds per signature, so a suspected sink is *deprioritized* before it's *discarded*:
- **Soft cap:** beyond N of one template/section, send further matches to a **low-priority (deferred) queue**, drained only after the normal queue empties. They still get crawled, just last.
- **Hard cap:** beyond M, **drop** further matches and record the drop count as completeness evidence.

A real-but-large section then degrades gracefully instead of hitting a cliff, while a true sink still can't consume the budget.

## The target can be in the filler

The most dangerous interaction with your own defenses: assuming the maze is pure junk and capping it away, when a target is planted *inside* those filler pages. A cap protects you from running forever but can skip the very page you need. So: when you're short of a **known count**, treat your caps as suspect — raise them (and the global `max_visited` with them) and re-crawl. Mazes are usually finite even when they look endless; a full crawl often reveals the cap was the only thing hiding the answer. Always **log what a cap dropped**, so "covered everything" is never a silent lie.

## Recognizing decoys

Content shaped like the target but placed to burn your time. Spend a **bounded** probe, record a reasoned decision, move on:
- **Format look-alikes** — target-shaped tokens that fail the exact rule (wrong length/prefix). A tight target regex rejects them automatically.
- **"Noise" images that invite a stego hunt.** Tell real stego from a decoy cheaply: a genuine hidden message has a high-entropy but *structureless* bit-plane; a decoy procedural pattern has a **periodic** low-bit stream (e.g. `0xAA 0xAA...`). Periodic LSB ⇒ decorative ⇒ stop. (And check the boring explanation first: a target "in an image" is often simply *drawn in its pixels* and needs a glance/OCR, not bit-plane analysis.)
- **Pagination/report sinks** whose rows are target-shaped but never valid.

## The bare-vs-formatted ambiguity

When the target has a wrapper, you'll sometimes find the **bare body** alone in a metadata field or comment. Is it the target unwrapped, or a decoy/hash?
- **Hash test:** compute md5/sha of obvious inputs (the resource bytes, a caption, the filename). If the bare value matches one, it's a fingerprint decoy.
- **Formatted beats bare, per container:** if the *same* container already yields a properly-wrapped target, treat a bare body found alongside it as a decoy; promote a bare body only when its container has nothing better. Rationale: a bare body is a weaker signal than a wrapped one.
- When genuinely ambiguous, **surface it as a candidate with evidence** and let validation decide — don't silently include or exclude.

## Genuine blocks vs bypassable ones

Some walls are real and out of scope; some are trivially bypassable misconfigurations. Distinguish with a **bounded** probe, then record the decision (the goal is *classification*, not bypassing controls — don't bypass a real one):
- A **client-trusted** geo/role header check flips on a spoofed header (`X-Forwarded-For`, `CF-IPCountry`, `X-Country-Code`, ...). Try a small fixed set once.
- A **genuine server-side** IP geo-block ignores all of them. If a bounded sweep changes nothing, it's real — a real browser on the same network would be equally blocked. Document it as out-of-scope rather than escalating to VPN/proxy.

The point is to tell "a real boundary is blocking me" from "my request is missing a header a legitimate client would send," so you neither give up on reachable content nor waste time forcing a real wall.

## Tuning defaults

Starting points; **raise them once you know the site is finite and targets live in the capped region**:
- `pattern_soft_limit` ~5, `pattern_hard_limit` ~50 — bounds numeric pagers; real content rarely shares one numeric template that many times.
- `section_soft_limit` ~50, `section_hard_limit` ~250 — covers a large-but-finite section while bounding an unbounded maze. If the site turns out small and finite with targets seeded in maze pages, raise these — the cap is now pure downside.
- `max_visited` — a global backstop *above* the site's true size. If your maze cap lets ~650 pages through, a `max_visited` of 500 stops you early; size it with headroom.
