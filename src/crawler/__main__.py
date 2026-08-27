"""Command-line entry point: ``python -m crawler [options]``.

Target URL and credentials are read from the config file (``crawler.toml`` by
default); every value can still be overridden with a flag or an environment
variable. See ``crawler.example.toml``.
"""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

from .config import DEFAULT_LIMITS, load_settings
from .crawler import Crawler


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="crawler", description=__doc__)
    p.add_argument("--config", type=Path, default=None,
                   help="path to the TOML config file (default: ./crawler.toml)")
    p.add_argument("--base-url", default=None, help="override [target].base_url")
    p.add_argument("--username", default=None, help="override [auth].username")
    p.add_argument("--password", default=None, help="override [auth].password")
    p.add_argument("--output", type=Path, default=Path("output"))
    p.add_argument("--max-fetches", type=int, default=DEFAULT_LIMITS.max_fetches)
    p.add_argument("--max-depth", type=int, default=DEFAULT_LIMITS.max_depth)
    p.add_argument("--delay", type=float, default=DEFAULT_LIMITS.delay_seconds)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    settings = load_settings(
        args.config,
        base_url=args.base_url,
        username=args.username,
        password=args.password,
    )
    limits = dataclasses.replace(
        DEFAULT_LIMITS,
        max_fetches=args.max_fetches,
        max_depth=args.max_depth,
        delay_seconds=args.delay,
    )
    crawler = Crawler(
        base_url=settings.base_url,
        username=settings.username,
        password=settings.password,
        output_dir=args.output,
        limits=limits,
    )
    result = crawler.run()

    print("\n" + result["report_markdown"])
    stats = result["stats"]
    print(
        f"\nDone: {stats['qualified_count']} qualifying finding(s) in "
        f"{stats['fetched']} fetches. Full report: {args.output}/report.md"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
