from crawler.config import DEFAULT_LIMITS
from crawler.urlnorm import canonicalize, in_scope, is_trap_shape

BASE = "http://54.214.7.161/"


def c(url, base=BASE):
    return canonicalize(url, base)


class TestCanonicalize:
    def test_relative_resolved_against_base(self):
        assert c("/docs/") == "http://54.214.7.161/docs/"

    def test_index_html_and_trailing_slash_and_bare_all_fold(self):
        variants = ["/blog", "/blog/", "/blog/index.html", "blog/index.html"]
        assert {c(v) for v in variants} == {"http://54.214.7.161/blog/"}

    def test_tracking_params_are_stripped(self):
        assert c("/help/?utm_source=internal") == "http://54.214.7.161/help/"
        assert c("/wiki/?v=7&ref=nav") == "http://54.214.7.161/wiki/"

    def test_semantic_params_are_kept_and_sorted(self):
        assert c("/report/?page=2") == "http://54.214.7.161/report/?page=2"
        assert c("/x/?b=2&a=1") == "http://54.214.7.161/x/?a=1&b=2"

    def test_fragment_removed(self):
        assert c("/docs/#section") == "http://54.214.7.161/docs/"

    def test_host_lowercased_and_default_port_dropped(self):
        assert c("http://54.214.7.161:80/docs") == "http://54.214.7.161/docs/"

    def test_dot_segments_collapsed(self):
        assert c("/docs/../wiki/./x/") == "http://54.214.7.161/wiki/x/"

    def test_static_asset_keeps_extension_no_trailing_slash(self):
        assert c("/static/js/main.js") == "http://54.214.7.161/static/js/main.js"

    def test_non_http_scheme_rejected(self):
        assert c("mailto:a@b.com") is None
        assert c("javascript:void(0)") is None


class TestScope:
    def test_same_host_in_scope(self):
        assert in_scope("http://54.214.7.161/x", "54.214.7.161")

    def test_other_host_out_of_scope(self):
        assert not in_scope("https://blog.example/careers", "54.214.7.161")


class TestTrapShape:
    def test_normal_url_is_fine(self):
        assert not is_trap_shape("http://54.214.7.161/wiki/rule-change/", DEFAULT_LIMITS)

    def test_excessive_path_depth_rejected(self):
        deep = "http://54.214.7.161/" + "/".join(f"s{i}" for i in range(20)) + "/"
        assert is_trap_shape(deep, DEFAULT_LIMITS)

    def test_repeated_segment_rejected(self):
        looping = "http://54.214.7.161/a/b/a/b/a/b/a/b/"
        assert is_trap_shape(looping, DEFAULT_LIMITS)

    def test_too_many_query_params_rejected(self):
        busy = "http://54.214.7.161/x/?" + "&".join(f"p{i}=1" for i in range(8))
        assert is_trap_shape(busy, DEFAULT_LIMITS)
