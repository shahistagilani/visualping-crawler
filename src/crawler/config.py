"""Configuration: runtime settings loaded from a file, plus tunable limits.

Target URL and credentials are **not** hard-coded. They come from a TOML config
file (``crawler.toml`` by default — copy ``crawler.example.toml``), and any of
them can be overridden by an environment variable or a CLI flag.

Resolution order (first non-empty wins): CLI flag → environment variable →
config file.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = "pattern-hunt-crawler/1.0 (+https://example.invalid/crawler)"

# Number of distinct qualifying targets expected on the site (``None`` = unknown).
TARGET_COUNT: int | None = 8

# A worked example / sample value published by the site that must NOT be counted.
EXAMPLE_PASSWORD = "VISUALPING{0000deadbeef0000}"

# Query parameters that never change which page you land on; dropped during
# canonicalisation so tracking-tagged links collapse onto one visited key.
NOISE_PARAMS = frozenset(
    {"ref", "v", "hl", "fbclid", "gclid", "sid", "session", "_", "cache"}
)

DEFAULT_CONFIG_PATH = Path(os.environ.get("CRAWLER_CONFIG", "crawler.toml"))


@dataclass(frozen=True)
class Settings:
    """Where to crawl and how to authenticate. Loaded, never hard-coded."""

    base_url: str
    username: str
    password: str


def load_settings(
    config_path: str | Path | None = None,
    *,
    base_url: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> Settings:
    """Build :class:`Settings` from (in order) explicit args, env vars, file.

    Raises ``SystemExit`` with a helpful message if anything is still missing.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    file_data: dict = {}
    if path.is_file():
        with open(path, "rb") as handle:
            file_data = tomllib.load(handle)

    target = file_data.get("target", {})
    auth = file_data.get("auth", {})

    resolved = Settings(
        base_url=base_url or os.environ.get("CRAWLER_BASE_URL") or target.get("base_url", ""),
        username=username or os.environ.get("CRAWLER_USER") or auth.get("username", ""),
        password=password or os.environ.get("CRAWLER_PASS") or auth.get("password", ""),
    )

    missing = [name for name in ("base_url", "username", "password") if not getattr(resolved, name)]
    if missing:
        raise SystemExit(
            f"crawler: missing required setting(s): {', '.join(missing)}.\n"
            f"Provide them in {path} (copy crawler.example.toml and edit), or via "
            f"the CRAWLER_BASE_URL / CRAWLER_USER / CRAWLER_PASS environment "
            f"variables, or the --base-url / --username / --password flags."
        )
    return resolved


@dataclass(frozen=True)
class Limits:
    """Every knob that bounds the crawl."""

    # --- hard budgets (unconditional stops) ---
    max_fetches: int = 2000
    max_depth: int = 60
    max_frontier: int = 20000
    max_body_bytes: int = 25 * 1024 * 1024
    max_redirects: int = 5
    wall_clock_seconds: float = 1800.0

    # --- per-request behaviour ---
    request_timeout: float = 15.0
    delay_seconds: float = 0.25
    retries: int = 3
    backoff_base: float = 0.5

    # --- loop / spider-trap guards ---
    max_values_per_param: int = 10  # e.g. ?page=1..10 then stop (numeric sink)
    max_path_depth: int = 16
    max_query_params: int = 6
    max_url_length: int = 2000
    max_segment_repeat: int = 3

    # transient HTTP statuses worth retrying
    retry_statuses: frozenset[int] = field(
        default_factory=lambda: frozenset({502, 503, 504})
    )


DEFAULT_LIMITS = Limits()
