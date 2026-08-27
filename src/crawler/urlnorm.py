"""URL canonicalisation, scope checking, and spider-trap shape rejection.

The golden rule (see crawler-best-practices.md Part 2.1): always compare the
*canonical* form of a URL against the visited set, never the raw href.
"""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .config import NOISE_PARAMS, Limits

_INDEX_FILES = {"index.html", "index.htm", "index.php"}
_DEFAULT_PORTS = {"http": 80, "https": 443}
_MULTISLASH = re.compile(r"/{2,}")


def canonicalize(url: str, base: str) -> str | None:
    """Return a stable canonical URL string, or ``None`` if not crawlable.

    Folds together the many ways this site links the same page: relative vs
    absolute, ``/x`` vs ``/x/`` vs ``/x/index.html``, tracking query params,
    and query-parameter ordering.
    """
    if not url:
        return None
    absolute = urljoin(base, url.strip())
    parts = urlsplit(absolute)

    if parts.scheme not in ("http", "https"):
        return None

    host = (parts.hostname or "").lower()
    if not host:
        return None
    netloc = host
    if parts.port and parts.port != _DEFAULT_PORTS.get(parts.scheme):
        netloc = f"{host}:{parts.port}"

    path = _normalize_path(parts.path)
    query = _clean_query(parts.query)
    return urlunsplit((parts.scheme, netloc, path, query, ""))


def in_scope(canonical_url: str, allowed_host: str) -> bool:
    """True only for URLs on the crawl's own host (case-insensitive)."""
    return urlsplit(canonical_url).hostname == allowed_host.lower()


def is_trap_shape(canonical_url: str, limits: Limits) -> bool:
    """Reject URLs whose *shape* signals a spider trap before we ever fetch."""
    if len(canonical_url) > limits.max_url_length:
        return True
    parts = urlsplit(canonical_url)
    segments = [s for s in parts.path.split("/") if s]
    if len(segments) > limits.max_path_depth:
        return True
    if segments and max(Counter(segments).values()) > limits.max_segment_repeat:
        return True
    if parts.query and len(parse_qsl(parts.query, keep_blank_values=True)) > limits.max_query_params:
        return True
    return False


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    path = _MULTISLASH.sub("/", path)
    segments = path.split("/")
    if segments[-1] in _INDEX_FILES:
        segments[-1] = ""
    path = "/".join(segments)
    if not path.startswith("/"):
        path = "/" + path
    last = path.rsplit("/", 1)[-1]
    if last and "." not in last:  # extension-less -> treat as a directory
        path += "/"
    return path or "/"


def _clean_query(query: str) -> str:
    if not query:
        return ""
    pairs = [
        (k, v)
        for k, v in parse_qsl(query, keep_blank_values=True)
        if k.lower() not in NOISE_PARAMS and not k.lower().startswith("utm_")
    ]
    pairs.sort()
    return urlencode(pairs)
