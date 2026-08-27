"""End-to-end crawl over an in-memory fake site (no network)."""

import dataclasses

from crawler.config import DEFAULT_LIMITS
from crawler.crawler import Crawler
from crawler.http import Response

FAST = dataclasses.replace(DEFAULT_LIMITS, delay_seconds=0.0)

PW_HOME = "VISUALPING{aaaaaaaaaaaaaaaa}"
PW_DEEP = "VISUALPING{bbbbbbbbbbbbbbbb}"
PW_JS = "VISUALPING{cccccccccccccccc}"

SITE = {
    "http://site.test/": (
        "text/html",
        f"""<a href="/docs/">docs</a>
            <a href="/dup/">dup</a>
            <script src="/static/app.js"></script>
            <a href="https://external.test/leak">offsite</a>
            <!-- {PW_HOME} -->""".encode(),
    ),
    "http://site.test/docs/": ("text/html", f"<p>{PW_DEEP}</p><a href='/docs/'>self</a>".encode()),
    "http://site.test/dup/": ("text/html", f"<p>{PW_DEEP}</p><a href='/docs/'>self</a>".encode()),
    "http://site.test/static/app.js": ("application/javascript", f'// {PW_JS}\nx="/hidden/";'.encode()),
    "http://site.test/hidden/": ("text/html", b"<p>nothing here</p>"),
    "https://external.test/leak": ("text/html", b"VISUALPING{ffffffffffffffff}"),
}


class FakeFetcher:
    def __init__(self):
        self.requested: list[str] = []

    def fetch(self, url: str) -> Response | None:
        self.requested.append(url)
        if url not in SITE:
            return None
        ct, body = SITE[url]
        return Response(url=url, status=200, content_type=ct, headers={}, body=body)


def run(tmp_path):
    fetcher = FakeFetcher()
    crawler = Crawler("http://site.test/", "u", "p", tmp_path, limits=FAST, fetcher=fetcher)
    result = crawler.run()
    return fetcher, result


def test_finds_passwords_in_comment_body_and_js(tmp_path):
    _, result = run(tmp_path)
    found = {f.password for f in result["findings"] if f.qualified}
    assert {PW_HOME, PW_DEEP, PW_JS} <= found


def test_stays_in_scope(tmp_path):
    fetcher, _ = run(tmp_path)
    assert not any("external.test" in u for u in fetcher.requested)
    assert "VISUALPING{ffffffffffffffff}" not in {
        f.password for f in run(tmp_path)[1]["findings"]
    }


def test_follows_js_discovered_link(tmp_path):
    fetcher, _ = run(tmp_path)
    assert "http://site.test/hidden/" in fetcher.requested


def test_duplicate_body_not_expanded_but_still_scanned(tmp_path):
    fetcher, result = run(tmp_path)
    # /dup/ has an identical body to /docs/; both are fetched...
    assert "http://site.test/dup/" in fetcher.requested
    # ...but the shared body is only counted once per password
    deep = [f for f in result["findings"] if f.password == PW_DEEP]
    assert len(deep) == 1


def test_writes_reports(tmp_path):
    run(tmp_path)
    assert (tmp_path / "report.md").exists()
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "pages").is_dir()


def test_report_counts_qualifying_passwords(tmp_path):
    _, result = run(tmp_path)
    assert result["stats"]["qualified_count"] == 3
