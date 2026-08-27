import base64

from crawler.config import EXAMPLE_PASSWORD
from crawler.scanner import PASSWORD_RE, scan

URL = "http://host/x"
REAL = "VISUALPING{0123456789abcdef}"


def _passwords(findings, *, qualified=None):
    return {
        f.password
        for f in findings
        if qualified is None or f.qualified is qualified
    }


class TestFormat:
    def test_regex_matches_spec_format_only(self):
        assert PASSWORD_RE.fullmatch("VISUALPING{0123456789abcdef}")
        assert not PASSWORD_RE.fullmatch("VISUALPING{0123456789ABCDEF}")  # upper hex
        assert not PASSWORD_RE.fullmatch("VISUALPING{0123}")  # too short

    def test_worked_example_is_ignored(self):
        findings = scan(URL, "text/html", {}, f"<pre>{EXAMPLE_PASSWORD}</pre>".encode())
        assert findings == []


class TestPlainBody:
    def test_finds_password_in_html_body(self):
        findings = scan(URL, "text/html", {}, f"<p>{REAL}</p>".encode())
        assert _passwords(findings, qualified=True) == {REAL}

    def test_finds_password_in_html_comment(self):
        findings = scan(URL, "text/html", {}, f"<!-- keep: {REAL} -->".encode())
        assert REAL in _passwords(findings, qualified=True)

    def test_finds_password_in_data_attribute(self):
        body = f'<body data-x="{REAL}">'.encode()
        assert REAL in _passwords(scan(URL, "text/html", {}, body), qualified=True)

    def test_finds_password_in_raw_bytes_when_body_not_utf8(self):
        body = b"\x80\x81" + REAL.encode() + b"\xfe"
        assert REAL in _passwords(scan(URL, "application/octet-stream", {}, body))


class TestRepresentationLadder:
    def test_utf16_le_body(self):
        body = b"prefix" + REAL.encode("utf-16-le") + b"suffix"
        assert REAL in _passwords(scan(URL, "image/jpeg", {}, body), qualified=True)

    def test_character_code_array(self):
        codes = ", ".join(str(ord(c)) for c in REAL)
        body = f"var beacon = [{codes}];".encode()
        assert REAL in _passwords(scan(URL, "application/javascript", {}, body), qualified=True)

    def test_hex_prefixed_character_code_array(self):
        codes = ", ".join(f"0x{ord(c):02x}" for c in REAL)
        body = f"[{codes}]".encode()
        assert REAL in _passwords(scan(URL, "application/javascript", {}, body), qualified=True)

    def test_html_entities(self):
        body = ("".join(f"&#{ord(c)};" for c in REAL)).encode()
        assert REAL in _passwords(scan(URL, "text/html", {}, body), qualified=True)

    def test_js_unicode_escapes(self):
        body = ("".join(f"\\u{ord(c):04x}" for c in REAL)).encode()
        assert REAL in _passwords(scan(URL, "application/javascript", {}, body), qualified=True)

    def test_base64_blob(self):
        blob = base64.b64encode(f"secret={REAL}".encode()).decode()
        findings = scan(URL, "text/html", {}, f"<code>{blob}</code>".encode())
        assert REAL in _passwords(findings, qualified=True)


class TestHeaders:
    def test_header_hit_is_recorded_but_disqualified(self):
        findings = scan(URL, "text/html", {"X-Staging": REAL}, b"<p>nothing</p>")
        assert _passwords(findings, qualified=False) == {REAL}
        assert _passwords(findings, qualified=True) == set()

    def test_body_hit_wins_over_same_value_in_header(self):
        findings = scan(URL, "text/html", {"X-Staging": REAL}, f"<p>{REAL}</p>".encode())
        assert _passwords(findings, qualified=True) == {REAL}
        assert _passwords(findings, qualified=False) == set()


class TestBareHexPromotion:
    def test_bare_16_hex_in_binary_becomes_candidate(self):
        body = b"\xff\xd8\xff\xfe\x00\x12" + b"5a6b01d97bfffdc3" + b"\xff\xd9"
        findings = scan(URL, "image/jpeg", {}, body)
        assert "VISUALPING{5a6b01d97bfffdc3}" in _passwords(findings, qualified=True)

    def test_bare_hex_suppressed_when_resource_has_a_wrapped_match(self):
        # field-visit.jpg shape: a wrapped value in UTF-16 metadata AND a bare
        # decoy in a COM segment. The wrapped one must win; the decoy dropped.
        body = (
            b"\xff\xe1" + REAL.encode("utf-16-le")
            + b"\xff\xfe\x00\x12" + b"5a6b01d97bfffdc3" + b"\xff\xd9"
        )
        passwords = _passwords(scan(URL, "image/jpeg", {}, body), qualified=True)
        assert REAL in passwords
        assert "VISUALPING{5a6b01d97bfffdc3}" not in passwords

    def test_bare_hex_not_scanned_in_text_resources(self):
        findings = scan(URL, "text/html", {}, b"commit 5a6b01d97bfffdc3 landed")
        assert findings == []
