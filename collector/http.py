"""Client HTTP « poli » : respect de robots.txt, délai par hôte, retries avec backoff.

Aucun contournement de protection anti-bot n'est effectué : une réponse 401/403/429 persistante
ou une page de challenge est remontée comme erreur et la source est marquée en conséquence.
"""

from __future__ import annotations

import gzip
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
from protego import Protego

from .log import get_logger, log

logger = get_logger(__name__)

CHALLENGE_MARKERS = ("Just a moment...", "cf-challenge", "captcha-delivery.com", "datadome")


class FetchError(Exception):
    def __init__(self, url: str, reason: str, status: int | None = None):
        super().__init__(f"{reason} ({status}) : {url}" if status else f"{reason} : {url}")
        self.url = url
        self.reason = reason
        self.status = status


class ListingRemoved(FetchError):
    """Annonce retirée : redirection vers une autre page ou « soft 404 » (page de liste en 200)."""

    def __init__(self, url: str, reason: str = "annonce retirée"):
        super().__init__(url, reason, 410)


class DisallowedByRobots(FetchError):
    def __init__(self, url: str):
        super().__init__(url, "interdit par robots.txt")


class BlockedError(FetchError):
    """Protection anti-bot détectée : on n'insiste pas."""


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)


class PoliteClient:
    def __init__(
        self,
        user_agent: str,
        default_delay: float = 1.5,
        timeout: float = 30.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        respect_robots: bool = True,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.user_agent = user_agent
        self.default_delay = default_delay
        self.max_retries = max_retries
        self.respect_robots = respect_robots
        self._sleep = sleep
        self._client = httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept-Language": "fr-FR,fr;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._robots: dict[str, Protego | None] = {}
        self._last_request: dict[str, float] = {}
        self._delays: dict[str, float] = {}
        self._lock = threading.Lock()
        self.request_count = 0

    def close(self) -> None:
        self._client.close()

    def set_delay(self, host: str, seconds: float) -> None:
        self._delays[host] = seconds

    # ------------------------------------------------------------------ robots.txt
    def _robots_for(self, scheme: str, host: str) -> Protego | None:
        key = f"{scheme}://{host}"
        if key not in self._robots:
            parser: Protego | None = None
            try:
                resp = self._raw_get(f"{key}/robots.txt", host)
                if resp.status_code == 200:
                    parser = Protego.parse(resp.text)
                elif resp.status_code in (401, 403):
                    # Accès à robots.txt refusé : par prudence, on considère tout interdit.
                    parser = Protego.parse("User-agent: *\nDisallow: /")
                # 404 / autre : pas de règles → tout autorisé (comportement standard RFC 9309).
            except httpx.HTTPError as exc:
                log(logger, logging.WARNING, "robots.txt inaccessible", host=host, error=str(exc))
                parser = Protego.parse("User-agent: *\nDisallow: /")
            self._robots[key] = parser
            if parser is not None:
                delay = parser.crawl_delay(self.user_agent)
                if delay:
                    self._delays[host] = max(self._delays.get(host, 0.0), float(delay))
        return self._robots[key]

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https"):
            return True
        robots = self._robots_for(parts.scheme, parts.netloc)
        return robots is None or robots.can_fetch(url, self.user_agent)

    def sitemaps(self, base_url: str) -> list[str]:
        parts = urlsplit(base_url)
        robots = self._robots_for(parts.scheme, parts.netloc)
        return list(robots.sitemaps) if robots else []

    # ------------------------------------------------------------------ requêtes
    def _throttle(self, host: str) -> None:
        delay = self._delays.get(host, self.default_delay)
        with self._lock:
            last = self._last_request.get(host)
            now = time.monotonic()
            wait = 0.0 if last is None else max(0.0, last + delay - now)
            self._last_request[host] = now + wait
        if wait > 0:
            self._sleep(wait)

    def _raw_get(self, url: str, host: str) -> httpx.Response:
        self._throttle(host)
        self.request_count += 1
        return self._client.get(url)

    def get(self, url: str) -> FetchResult:
        if url.startswith("file://"):
            path = url[len("file://") :]
            with open(path, "rb") as fh:
                data = fh.read()
            if path.endswith(".gz"):
                data = gzip.decompress(data)
            return FetchResult(url=url, status=200, text=data.decode("utf-8"))
        if not self.allowed(url):
            raise DisallowedByRobots(url)
        host = urlsplit(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._raw_get(url, host)
            except httpx.HTTPError as exc:
                last_exc = exc
                self._sleep(2**attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = resp.headers.get("retry-after", "")
                wait = float(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1)
                last_exc = FetchError(url, "réponse temporaire", resp.status_code)
                self._sleep(min(wait, 60))
                continue
            content = resp.content
            if url.endswith(".gz") and content[:2] == b"\x1f\x8b":
                content = gzip.decompress(content)
            text = content.decode(resp.encoding or "utf-8", errors="replace")
            if resp.status_code in (401, 403) or any(m in text[:5000] for m in CHALLENGE_MARKERS):
                raise BlockedError(url, "protection anti-bot ou accès refusé", resp.status_code)
            if resp.status_code >= 400:
                raise FetchError(url, "erreur HTTP", resp.status_code)
            return FetchResult(url=str(resp.url), status=resp.status_code, text=text, headers=dict(resp.headers))
        raise FetchError(url, f"échec après {self.max_retries + 1} tentatives : {last_exc}")


class PlaywrightRenderer:
    """Rendu JavaScript optionnel. Utilisé uniquement pour les sources déclarant ``render: playwright``.

    robots.txt est vérifié par le ``PoliteClient`` avant chaque rendu.
    """

    def __init__(self, client: PoliteClient):
        self.client = client
        self._pw = None
        self._browser = None

    def render(self, url: str, wait_selector: str | None = None) -> FetchResult:
        if not self.client.allowed(url):
            raise DisallowedByRobots(url)
        if self._browser is None:
            from playwright.sync_api import sync_playwright  # import paresseux : dépendance optionnelle

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch()
        host = urlsplit(url).netloc
        self.client._throttle(host)
        page = self._browser.new_page(user_agent=self.client.user_agent)
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=15000)
            html = page.content()
            status = resp.status if resp else 0
        finally:
            page.close()
        if status in (401, 403) or any(m in html[:5000] for m in CHALLENGE_MARKERS):
            raise BlockedError(url, "protection anti-bot ou accès refusé", status)
        return FetchResult(url=url, status=status, text=html)

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()
