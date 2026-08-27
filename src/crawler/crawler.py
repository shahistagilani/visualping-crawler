"""The orchestrator: breadth-first walk from the seed, wiring together the
fetcher, link extractor, secret scanner, frontier, and storage.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urlsplit

from . import report
from .config import DEFAULT_LIMITS, Limits
from .extract import extract_links
from .frontier import Frontier
from .http import Fetcher
from .images import ocr_matches, outlier_reason
from .scanner import Finding, scan
from .storage import Storage
from .urlnorm import canonicalize, in_scope


class Crawler:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        output_dir: Path,
        limits: Limits = DEFAULT_LIMITS,
        fetcher: Fetcher | None = None,
    ) -> None:
        self._base_url = base_url
        self._allowed_host = (urlsplit(base_url).hostname or "").lower()
        self._limits = limits
        self._fetcher = fetcher or Fetcher(username, password, limits)
        self._frontier = Frontier(limits)
        self._storage = Storage(output_dir)

        self._findings: dict[str, Finding] = {}
        self._body_hashes: set[str] = set()
        self._log: list[dict] = []
        self._review: list[dict] = []  # images a human should eyeball
        self._fetched = 0
        self._started_at = 0.0

    # -- public API ---------------------------------------------------------

    def run(self) -> dict:
        self._started_at = time.monotonic()
        seed = canonicalize(self._base_url, self._base_url)
        if seed is None:
            raise ValueError(f"un-crawlable base URL: {self._base_url}")
        self._frontier.add(seed, 0)

        while self._frontier and not self._budget_exhausted():
            url, depth = self._frontier.pop()
            self._process(url, depth)
            time.sleep(self._limits.delay_seconds)

        return self._finalize()

    @property
    def findings(self) -> list[Finding]:
        return list(self._findings.values())

    # -- internals --------------------------------------------------------

    def _budget_exhausted(self) -> bool:
        if self._fetched >= self._limits.max_fetches:
            return True
        elapsed = time.monotonic() - self._started_at
        return elapsed >= self._limits.wall_clock_seconds

    def _process(self, url: str, depth: int) -> None:
        response = self._fetcher.fetch(url)
        if response is None:
            self._log.append({"url": url, "status": "ERROR", "depth": depth})
            return

        self._fetched += 1
        self._storage.save_body(response.url, response.content_type, response.body)

        new_here = 0
        for finding in scan(response.url, response.content_type, response.headers, response.body):
            if self._record(finding):
                new_here += 1

        if response.content_type.startswith("image/"):
            new_here += self._inspect_image(response.url, response.body)

        record = {
            "url": url,
            "final_url": response.url,
            "status": response.status,
            "content_type": response.content_type,
            "bytes": len(response.body),
            "depth": depth,
            "new_findings": new_here,
        }

        body_hash = hashlib.sha256(response.body).hexdigest()
        if body_hash in self._body_hashes:
            record["note"] = "duplicate body — not expanded"
            self._log.append(record)
            return
        self._body_hashes.add(body_hash)

        enqueued = 0
        for raw in extract_links(response):
            target = canonicalize(raw, response.url)
            if target and in_scope(target, self._allowed_host):
                if self._frontier.add(target, depth + 1):
                    enqueued += 1
        record["links_enqueued"] = enqueued
        self._log.append(record)
        print(
            f"[{self._fetched:3}] {response.status} {response.content_type:24} "
            f"+{enqueued:2} links  {url}"
        )

    def _inspect_image(self, url: str, body: bytes) -> int:
        """OCR the image; flag it for manual review if it's a dimensional outlier
        and produced no finding. Returns the count of new findings."""
        new = 0
        for password in ocr_matches(body):
            if self._record(Finding(password, url, "image pixels (OCR)", True)):
                new += 1
        already_found = any(f.source_url == url for f in self._findings.values())
        if not already_found:
            reason = outlier_reason(body)
            if reason:
                self._review.append({"url": url, "reason": reason})
        return new

    def _record(self, finding: Finding) -> bool:
        """Keep one finding per password; a qualified hit upgrades a header-only one."""
        existing = self._findings.get(finding.password)
        if existing is None:
            self._findings[finding.password] = finding
            return finding.qualified
        if finding.qualified and not existing.qualified:
            self._findings[finding.password] = finding
        return False

    def _finalize(self) -> dict:
        stats = {
            "fetched": self._fetched,
            "discovered": self._frontier.discovered,
            "duration_seconds": round(time.monotonic() - self._started_at, 1),
            "rejected": dict(self._frontier.rejected),
            "rejected_urls": {k: sorted(set(v)) for k, v in self._frontier.rejected_urls.items()},
            "qualified_count": sum(1 for f in self._findings.values() if f.qualified),
            "review": self._review,
        }
        findings = list(self._findings.values())
        self._storage.write_json("report.json", report.build_json(findings, self._log, stats))
        md = report.build_markdown(findings, self._log, stats)
        self._storage.write_text("report.md", md)
        return {"stats": stats, "findings": findings, "report_markdown": md}
