"""Fetcher tests using a fake session — no network."""

import dataclasses

import pytest
import requests

from crawler.config import DEFAULT_LIMITS
from crawler.http import Fetcher

NO_DELAY = dataclasses.replace(DEFAULT_LIMITS, backoff_base=0.0, retries=2)


class FakeRaw:
    def __init__(self, body: bytes):
        self._body = body

    def __iter__(self):
        yield self._body


class FakeHTTPResponse:
    def __init__(self, status=200, body=b"hi", content_type="text/html", url="http://h/x"):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.url = url
        self._body = body
        self.closed = False

    def iter_content(self, _size):
        yield self._body

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.auth = None
        self.headers = {}
        self.max_redirects = 0

    def get(self, url, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_fetcher(session):
    return Fetcher("user", "pass", NO_DELAY, session=session)


def test_auth_and_user_agent_are_set_on_session():
    session = FakeSession([FakeHTTPResponse()])
    make_fetcher(session)
    assert session.auth == ("user", "pass")
    assert "User-Agent" in session.headers


def test_successful_fetch_returns_parsed_response():
    session = FakeSession([FakeHTTPResponse(body=b"<p>x</p>", content_type="text/html; charset=utf-8")])
    resp = make_fetcher(session).fetch("http://h/x")
    assert resp is not None
    assert resp.status == 200
    assert resp.content_type == "text/html"  # parameters stripped
    assert resp.body == b"<p>x</p>"


def test_retries_on_timeout_then_succeeds():
    session = FakeSession([requests.Timeout(), FakeHTTPResponse(body=b"ok")])
    resp = make_fetcher(session).fetch("http://h/x")
    assert resp is not None and resp.body == b"ok"
    assert session.calls == 2


def test_retries_on_transient_5xx_status():
    session = FakeSession([FakeHTTPResponse(status=503), FakeHTTPResponse(status=200, body=b"done")])
    resp = make_fetcher(session).fetch("http://h/x")
    assert resp is not None and resp.status == 200


def test_gives_up_after_retry_budget_and_returns_none():
    session = FakeSession([requests.ConnectionError()] * 3)
    assert make_fetcher(session).fetch("http://h/x") is None
    assert session.calls == 3  # 1 initial + 2 retries


def test_body_is_capped_at_limit():
    limits = dataclasses.replace(NO_DELAY, max_body_bytes=4)
    session = FakeSession([FakeHTTPResponse(body=b"0123456789")])
    resp = Fetcher("u", "p", limits, session=session).fetch("http://h/x")
    assert resp is not None and len(resp.body) == 4
