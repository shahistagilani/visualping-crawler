"""Link discovery.

"Not every link is an ``<a>`` tag": this module also pulls references out of
other HTML elements, inline CSS/JS, HTML comments, standalone stylesheets, and
JavaScript string literals (which is how this site's nav is really built).
Returned values are raw href strings; the caller canonicalises and scope-checks.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Comment

from .http import Response

# (tag, attribute) pairs that carry a URL to another resource.
_URL_ATTRS = [
    ("a", "href"),
    ("link", "href"),
    ("script", "src"),
    ("img", "src"),
    ("iframe", "src"),
    ("frame", "src"),
    ("form", "action"),
    ("area", "href"),
    ("object", "data"),
    ("embed", "src"),
    ("source", "src"),
    ("video", "src"),
    ("audio", "src"),
    ("track", "src"),
]

_CSS_URL = re.compile(r"""url\(\s*['"]?([^'")]+?)['"]?\s*\)""", re.IGNORECASE)
_CSS_IMPORT = re.compile(r"""@import\s+['"]([^'"]+)['"]""", re.IGNORECASE)
# Quoted absolute-path or dot-relative string literals inside a script blob.
_JS_PATH = re.compile(r"""['"]((?:\.{0,2}/)[^'"\s>]+)['"]""")
# Bare (unquoted) URLs / multi-segment paths, e.g. inside an HTML comment.
_FREEFORM_URL = re.compile(
    r"""https?://[^\s'"<>)]+|/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)+/?"""
)
_META_REFRESH_URL = re.compile(r"url\s*=\s*(.+)", re.IGNORECASE)


def extract_links(response: Response) -> set[str]:
    """Return the set of raw link strings found in ``response``."""
    ct = response.content_type
    text = response.body.decode("utf-8", errors="replace")
    if "html" in ct:
        return _from_html(text)
    if ct.endswith("/css"):
        return _from_css(text)
    if "javascript" in ct or "ecmascript" in ct or ct.endswith("/json"):
        return _from_script(text)
    return set()


def _from_html(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: set[str] = set()

    for tag, attr in _URL_ATTRS:
        for el in soup.find_all(tag):
            value = el.get(attr)
            if value:
                links.add(value.strip())

    for el in soup.find_all(attrs={"srcset": True}):
        for candidate in el["srcset"].split(","):
            token = candidate.strip().split(" ")[0]
            if token:
                links.add(token)

    for el in soup.find_all("meta", attrs={"http-equiv": re.compile("refresh", re.I)}):
        match = _META_REFRESH_URL.search(el.get("content", ""))
        if match:
            links.add(match.group(1).strip().strip("'\""))

    for el in soup.find_all(style=True):
        links |= _from_css(el["style"])

    for script in soup.find_all("script"):
        if script.string:
            links |= _from_script(script.string)

    for style in soup.find_all("style"):
        if style.string:
            links |= _from_css(style.string)

    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        links |= _from_freeform(str(comment))

    return {link for link in links if _is_meaningful(link)}


def _from_freeform(text: str) -> set[str]:
    """Bare URLs / multi-segment paths in unquoted text (e.g. HTML comments)."""
    return {m.strip() for m in _FREEFORM_URL.findall(text) if _is_meaningful(m.strip())}


def _from_css(css: str) -> set[str]:
    found = set(_CSS_URL.findall(css)) | set(_CSS_IMPORT.findall(css))
    return {link.strip() for link in found if _is_meaningful(link.strip())}


def _from_script(script: str) -> set[str]:
    return {m.strip() for m in _JS_PATH.findall(script) if _is_meaningful(m.strip())}


def _is_meaningful(link: str) -> bool:
    if not link or link in ("#", "/"):
        return False
    lowered = link.lower()
    return not lowered.startswith(("javascript:", "mailto:", "tel:", "data:", "#"))
