import pytest

from collector.http import BlockedError, DisallowedByRobots, FetchError

from .conftest import FakeSite

ROBOTS = "User-agent: *\nDisallow: /prive/\nDisallow: /*?sort=\nSitemap: https://a.example/sitemap.xml\n"


def test_robots_respected_with_wildcards():
    site = FakeSite({"https://a.example/robots.txt": ROBOTS, "https://a.example/ok": "bonjour"})
    client = site.client()
    assert client.get("https://a.example/ok").text == "bonjour"
    with pytest.raises(DisallowedByRobots):
        client.get("https://a.example/prive/page")
    assert not client.allowed("https://a.example/liste?sort=prix")
    assert client.sitemaps("https://a.example") == ["https://a.example/sitemap.xml"]
    assert site.hits["https://a.example/robots.txt"] == 1  # mis en cache


def test_robots_forbidden_means_disallow_all():
    site = FakeSite({"https://b.example/robots.txt": (403, "no")})
    assert not site.client().allowed("https://b.example/anything")


def test_missing_robots_allows_everything():
    site = FakeSite({"https://c.example/page": "ok"})
    assert site.client().get("https://c.example/page").text == "ok"


def test_retries_on_server_error_then_succeeds():
    site = FakeSite({"https://d.example/robots.txt": (404, "")})
    calls = {"n": 0}
    original = site.handler

    def flaky(request):
        if request.url.path == "/page":
            calls["n"] += 1
            if calls["n"] < 3:
                import httpx

                return httpx.Response(503, text="busy")
            import httpx

            return httpx.Response(200, text="enfin")
        return original(request)

    site.handler = flaky  # type: ignore[method-assign]
    assert site.client().get("https://d.example/page").text == "enfin"
    assert calls["n"] == 3


def test_challenge_page_is_reported_as_blocked():
    site = FakeSite({"https://e.example/page": "<title>Just a moment...</title>"})
    with pytest.raises(BlockedError):
        site.client().get("https://e.example/page")


def test_404_raises_fetch_error_with_status():
    site = FakeSite()
    with pytest.raises(FetchError) as exc:
        site.client().get("https://f.example/absent")
    assert exc.value.status == 404
