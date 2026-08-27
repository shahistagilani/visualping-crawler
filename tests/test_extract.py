from crawler.extract import extract_links
from crawler.http import Response


def html_response(body: str) -> Response:
    return Response(
        url="http://54.214.7.161/",
        status=200,
        content_type="text/html",
        headers={},
        body=body.encode(),
    )


def test_extracts_from_many_element_types():
    body = """
    <link rel="stylesheet" href="/static/css/style.css">
    <script src="/static/js/main.js"></script>
    <a href="/docs/">Docs</a>
    <img src="/static/img/a.png">
    <iframe src="/embed/x/"></iframe>
    <form action="/search/"></form>
    """
    links = extract_links(html_response(body))
    assert {"/static/css/style.css", "/static/js/main.js", "/docs/",
            "/static/img/a.png", "/embed/x/", "/search/"} <= links


def test_extracts_paths_from_inline_script_string_literals():
    body = """
    <script>
      var MENU = [
        { path: "/docs/upstream-sample-channel/", label: "x" },
        { path: "/wiki/shard-schedule/", label: "y" }
      ];
    </script>
    """
    links = extract_links(html_response(body))
    assert "/docs/upstream-sample-channel/" in links
    assert "/wiki/shard-schedule/" in links


def test_extracts_from_standalone_javascript_file():
    resp = Response(
        url="http://54.214.7.161/static/js/main.js",
        status=200,
        content_type="application/javascript",
        headers={},
        body=b'a.href = "/notes/archive-region/";',
    )
    assert "/notes/archive-region/" in extract_links(resp)


def test_extracts_url_from_css():
    resp = Response(
        url="http://54.214.7.161/static/css/style.css",
        status=200,
        content_type="text/css",
        headers={},
        body=b"body { background: url('/static/img/bg.png'); } @import '/static/css/more.css';",
    )
    links = extract_links(resp)
    assert {"/static/img/bg.png", "/static/css/more.css"} <= links


def test_extracts_from_html_comment():
    links = extract_links(html_response('<!-- see also /wiki/hidden-page/ -->'))
    assert "/wiki/hidden-page/" in links


def test_ignores_non_navigational_schemes():
    body = '<a href="mailto:x@y.com">m</a><a href="javascript:void(0)">j</a><a href="#top">t</a>'
    assert extract_links(html_response(body)) == set()
