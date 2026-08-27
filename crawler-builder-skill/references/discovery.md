# Discovery: Finding Every Resource and State

This is the detailed, code-writing version of *"follow every kind of link"* from the main guide — the full list of ways a site can hand you a file, and how to extract them all. You can't find something in a file you never downloaded, so treat every page as pointing to many other files (not just its clickable links), and treat an app built by scripts as having many *states*, not just addresses. If this list ever feels incomplete for a site, go back to the plain question — *"what are all the ways this site could hand me a file?"* — and add whatever it surfaces.

## Table of contents
- [URL identity: canonicalize before scheduling](#url-identity-canonicalize-before-scheduling)
- [Priority queue, not plain FIFO](#priority-queue-not-plain-fifo)
- [Static HTML carriers (all of them)](#static-html-carriers-all-of-them)
- [CSS and JavaScript graph expansion](#css-and-javascript-graph-expansion)
- [Well-known files worth seeding](#well-known-files-worth-seeding)
- [Browser-assisted discovery](#browser-assisted-discovery)
- [Safe interaction strategy](#safe-interaction-strategy)
- [State-explosion control](#state-explosion-control)

## URL identity: canonicalize before scheduling

For every candidate URL, before it enters the queue:

1. Resolve relative refs against the **response** URL (respect a document's `<base href>`).
2. Allow only `http`/`https`. Reject `javascript:`, `data:`, `file:`, `mailto:`, `blob:`, `about:`, and malformed URLs as crawl targets.
3. Lowercase scheme + host; normalize default ports.
4. Drop the fragment (`#...`) — never sent to the server, so not a distinct resource.
5. **Preserve query parameters by default** — `?page=2` is a different resource.
6. Enforce the origin/path allow-list *before* queuing.

Keep **both** the requested canonical URL and the final URL after redirects. A content hash helps skip re-*parsing* identical bodies but must **not** replace URL identity — the same content at two URLs can link onward differently.

**Dedup-key nuance:** strip only *known tracking* params (`utm_*`, `ref`, `hl`, ...) from the dedup key; keep content-selecting params (`page`, `id`, `q`). Getting this wrong is a classic self-inflicted explosion — treat `?ref=a` and `?ref=b` as distinct and a maze balloons; strip `?page=` and you collapse a real paginated resource into one.

## Priority queue, not plain FIFO

Reserve budget for high-confidence routes so a large procedural section can't starve an obvious menu link. Suggested order:

1. Seeds and explicitly-advertised routes (nav menus, JS route tables). **May bypass sink caps** — see `decoys-and-pitfalls.md`.
2. HTML pages, frames, API/document endpoints referenced directly by pages.
3. JavaScript, CSS, manifests, source maps.
4. Browser-observed network requests and popup routes.
5. Embedded / downloadable assets.
6. Low-confidence URLs inferred from scripts or transformed text.

Attach to every task: `url`, parent URL, discovery method, depth, request variant, priority, attempt count — that metadata is also your provenance and your debugging lifeline.

## Static HTML carriers (all of them)

Parsing only `a[href]` is the #1 cause of under-crawling. Extract from:

- **Navigation:** `a[href]`, `area[href]`, `link[href]` (incl. `rel=canonical`/`alternate`/`preload`/`icon`/`manifest`), `base[href]`.
- **Embedding:** `iframe[src]`, `frame[src]`, `object[data]`, `embed[src]`.
- **Resources:** `script[src]`, `img[src]`, `img[srcset]`, `source[src]`/`source[srcset]`, `video[src]`, `audio[src]`, `track[src]`.
- **Navigation hints:** `form[action]` (a GET form is a navigable URL), `meta[http-equiv=refresh]` (parse the `url=` out of `content`).
- **Application hints:** URL-like `data-*` and custom-element/ARIA attributes — promote only ones that resolve in-scope.

Parse `srcset` correctly — comma-separated, each candidate's first token is a URL. Skip non-navigable schemes and fragment-only hrefs.

## CSS and JavaScript graph expansion

**CSS** leads to content and assets via `@import` and `url(...)` (in linked stylesheets, `<style>` blocks, and inline `style=`). Extract from all three.

**JavaScript** exposes routes that never appear as anchors:
- route tables / nav data arrays (`{ path: "/docs/x" }`, `href:`/`url:` keys);
- `sourceMappingURL=` → fetch the **source map** if in-scope; it often holds original sources and readable constants absent from the minified bundle;
- static `import` targets and obvious `fetch("/api/...")` / XHR paths;
- same-origin-looking absolute path string literals (`"/..."`).

**Heuristic discipline:** prefer a JS parser or string-literal extractor over broad regexes, and only promote a string that looks like an in-scope URL/path. Queuing every string in a minified bundle floods the queue. Promote JS literals at **normal** priority unless they come from an obvious small nav table.

## Well-known files worth seeding

A browser or web convention consults these even when nothing links them (for *discovery*, never to bypass controls):
- `/sitemap.xml`, `/sitemap_index.xml` — routinely list pages nothing links to.
- `/robots.txt` — read for `Sitemap:` and path *hints*; obey its restrictions.
- `/favicon.ico`, `/manifest.json`, `/site.webmanifest`, `/apple-touch-icon.png`.
- Per-bundle: `<bundle>.js.map`.

Cheap; occasionally the only route to a resource.

## Browser-assisted discovery

Use a headless browser (Playwright or equivalent) **only** when static extraction is insufficient — a SPA, client-built routes, or a content plateau with targets missing. Use the browser as a **discovery engine**; keep the HTTP client as the primary **inspection engine** (but also scan browser-observed bodies, since runtime responses can depend on browser state).

Observe passively first (interception is less faithful and adds timing bugs):
- document + frame navigations; all requests/responses (and bodies where exposed);
- popup / new-tab URLs; client route changes (`pushState`/`replaceState`/`popstate`);
- DOM mutations, console errors; service-worker / runtime API requests.

Configure auth at the **browser-context** level so authorized subresources carry it.

## Safe interaction strategy

To reach states behind clicks without side effects:
1. Load a route; wait for a real readiness signal (not blind `networkidle` on a polling app).
2. Capture observed routes + network resources.
3. Enumerate **visible, enabled, navigation-like** controls: anchors, buttons, `role=link/button`, custom controls.
4. **Exclude likely state-changing controls** by method/label/type/policy (submit, delete, buy, send, publish).
5. Click one candidate; observe navigation/popups/network/DOM; capture discoveries.
6. Restore clean state (fresh page/context, or a reliable reload) before the next candidate.

Identify elements by a **semantic signature** (accessible name, role/tag, stable attributes, locator fallback), never a fragile ordinal. Cap interactions per route; record skips and why.

## State-explosion control

Browser crawling explores **states**, not just URLs. Use a state key = canonical URL + a **bounded fingerprint** of relevant DOM/app state. Prefer fresh contexts for determinism when auth/cost allow (history back-navigation is faster but unreliable in many SPAs). Cap total states and per-route interactions exactly as you cap URLs.
