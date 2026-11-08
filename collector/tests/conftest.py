from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from collector.config import Settings, SourceConfig, load_departments
from collector.connectors.base import ConnectorContext
from collector.geo import GeoIndex
from collector.http import PoliteClient

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeSite:
    """Serveur HTTP simulé : URL → (statut, corps). Compte les requêtes."""

    def __init__(self, pages: dict[str, tuple[int, str] | str] | None = None):
        self.pages: dict[str, tuple[int, str]] = {}
        self.hits: dict[str, int] = {}
        for url, page in (pages or {}).items():
            self.set(url, page)

    def set(self, url: str, page: tuple[int, str] | str) -> None:
        self.pages[url] = page if isinstance(page, tuple) else (200, page)

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.hits[url] = self.hits.get(url, 0) + 1
        status, body = self.pages.get(url, (404, "not found"))
        return httpx.Response(status, text=body)

    def client(self) -> PoliteClient:
        return PoliteClient("FindImmoTest/1.0", transport=httpx.MockTransport(self.handler), sleep=lambda _s: None)


@pytest.fixture(scope="session")
def geo() -> GeoIndex:
    return GeoIndex.load()


@pytest.fixture(scope="session")
def departments() -> set[str]:
    return {d.code for d in load_departments()}


@pytest.fixture
def settings() -> Settings:
    return Settings()


def make_source(**kwargs) -> SourceConfig:
    base = {"id": "test", "name": "Test", "domain": "agence-test.example", "url": "https://agence-test.example",
            "method": "sitemap_jsonld", "enabled": True, "rate_limit_seconds": 0}
    base.update(kwargs)
    return SourceConfig.model_validate(base)


def make_ctx(client: PoliteClient, geo: GeoIndex, departments: set[str]) -> ConnectorContext:
    return ConnectorContext(client=client, geo=geo, departments=departments)
