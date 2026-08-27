"""Authenticated HTTP fetching: one session, auth on every request, retries,
timeouts, and a hard body-size cap so no response can become a download sink.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

from .config import Limits, USER_AGENT


@dataclass(frozen=True)
class Response:
    """The subset of an HTTP response the rest of the crawler needs."""

    url: str  # final URL after redirects
    status: int
    content_type: str  # bare type, lower-cased, no parameters
    headers: dict[str, str]
    body: bytes

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class Fetcher:
    """Wraps a :class:`requests.Session` with the crawl's fetch policy."""

    def __init__(
        self,
        username: str,
        password: str,
        limits: Limits,
        session: requests.Session | None = None,
    ) -> None:
        self._limits = limits
        self._session = session or requests.Session()
        self._session.auth = (username, password)
        self._session.headers["User-Agent"] = USER_AGENT
        self._session.max_redirects = limits.max_redirects

    def fetch(self, url: str) -> Response | None:
        """GET ``url``, returning a :class:`Response` or ``None`` on failure."""
        last_error: Exception | None = None
        for attempt in range(self._limits.retries + 1):
            try:
                resp = self._session.get(
                    url,
                    timeout=self._limits.request_timeout,
                    stream=True,
                    allow_redirects=True,
                )
                if resp.status_code in self._limits.retry_statuses:
                    resp.close()
                    self._sleep_backoff(attempt)
                    continue
                return self._build_response(resp)
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                self._sleep_backoff(attempt)
            except requests.TooManyRedirects as exc:
                last_error = exc
                break
            except requests.RequestException as exc:
                last_error = exc
                break
        if last_error is not None:
            print(f"  ! fetch failed: {url} ({last_error})")
        return None

    def _build_response(self, resp: requests.Response) -> Response:
        body = self._read_capped(resp)
        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        return Response(
            url=resp.url,
            status=resp.status_code,
            content_type=content_type,
            headers=dict(resp.headers),
            body=body,
        )

    def _read_capped(self, resp: requests.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_content(8192):
            chunks.append(chunk)
            total += len(chunk)
            if total >= self._limits.max_body_bytes:
                break
        resp.close()
        return b"".join(chunks)[: self._limits.max_body_bytes]

    def _sleep_backoff(self, attempt: int) -> None:
        time.sleep(self._limits.backoff_base * (2**attempt))
