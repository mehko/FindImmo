"""Association méthode/adaptateur → classe de connecteur."""

from __future__ import annotations

from ..config import SourceConfig
from .adapters.era import EraConnector
from .adapters.foncia import FonciaConnector
from .adapters.hektor import HektorConnector
from .adapters.human import HumanConnector
from .adapters.laforet import LaforetConnector
from .adapters.remax import RemaxConnector
from .base import BaseConnector, ConnectorContext
from .feed import FeedConnector
from .html import HtmlConnector
from .jsonld import JsonLdConnector

METHODS: dict[str, type[BaseConnector]] = {
    "sitemap_jsonld": JsonLdConnector,
    "html": HtmlConnector,
    "feed": FeedConnector,
}

ADAPTERS: dict[str, type[BaseConnector]] = {
    "era": EraConnector,
    "foncia": FonciaConnector,
    "hektor": HektorConnector,
    "human": HumanConnector,
    "laforet": LaforetConnector,
    "remax": RemaxConnector,
}


def build_connector(source: SourceConfig, ctx: ConnectorContext) -> BaseConnector:
    if source.method == "adapter":
        if not source.adapter or source.adapter not in ADAPTERS:
            raise ValueError(f"{source.id} : adaptateur inconnu « {source.adapter} »")
        return ADAPTERS[source.adapter](source, ctx)
    if source.method not in METHODS:
        raise ValueError(f"{source.id} : méthode inconnue « {source.method} »")
    return METHODS[source.method](source, ctx)
