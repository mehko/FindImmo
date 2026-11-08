"""Interface commune des connecteurs.

Un connecteur fait deux choses :

1. ``discover()`` : énumérer les références d'annonces de la source (sitemap, flux, pages de liste).
   Une découverte terminée sans exception est considérée comme **exhaustive** : c'est la condition
   pour qu'une annonce absente passe en ``unavailable_unconfirmed``.
2. ``fetch_detail(ref)`` : récupérer et analyser la page détail d'une référence → ``RawListing``.

Le choix des références à récupérer (nouvelles, modifiées, anciennes) et le budget sont gérés par
``collector.collect`` : les connecteurs restent simples et sans état.
"""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field

from ..config import SourceConfig
from ..geo import GeoIndex, department_from_postal_code
from ..http import PlaywrightRenderer, PoliteClient
from ..models import ListingRef, RawListing


def page_signature(html: str) -> str:
    """Résumé court d'une page (taille, titre, JSON-LD) pour comprendre un échec d'analyse."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip()[:80] if m else "sans titre"
    return f"{len(html)} o, titre « {title} », JSON-LD×{html.count('application/ld+json')}"


@dataclass
class ConnectorContext:
    client: PoliteClient
    geo: GeoIndex
    departments: set[str]
    renderer: PlaywrightRenderer | None = None
    deadline: float = field(default_factory=lambda: time.monotonic() + 3600)

    def time_left(self) -> float:
        return self.deadline - time.monotonic()


class BaseConnector(ABC):
    #: Nom de la méthode dans ``config/sources.yaml``
    method: str = ""

    def __init__(self, source: SourceConfig, ctx: ConnectorContext):
        self.source = source
        self.ctx = ctx
        self.options = source.options
        #: Signature de la dernière page téléchargée (diagnostic des échecs d'analyse)
        self.last_page_info: str = ""

    # ---------------------------------------------------------------- API publique
    @abstractmethod
    def discover(self) -> Iterator[ListingRef]:
        """Énumère toutes les références d'annonces de la source."""

    def fetch_detail(self, ref: ListingRef) -> RawListing | None:
        if ref.raw is not None:
            return ref.raw
        html = self.fetch_page(ref.url)
        return self.parse_detail(html, ref)

    def parse_detail(self, html: str, ref: ListingRef) -> RawListing | None:  # pragma: no cover - surchargé
        raise NotImplementedError(f"{type(self).__name__} ne sait pas analyser une page détail")

    # ---------------------------------------------------------------- utilitaires
    def fetch_page(self, url: str) -> str:
        if self.source.render == "playwright":
            if self.ctx.renderer is None:
                self.ctx.renderer = PlaywrightRenderer(self.ctx.client)
            text = self.ctx.renderer.render(url, self.options.get("wait_selector")).text
        else:
            text = self.ctx.client.get(url).text
        self.last_page_info = page_signature(text)
        return text

    def ref_in_scope(self, ref: ListingRef) -> bool | None:
        """Pré-filtrage géographique avant téléchargement. ``None`` = impossible à déterminer."""
        dep = ref.department_hint or department_from_postal_code(ref.postal_code_hint)
        if dep is None:
            return None
        return dep in self.ctx.departments

    def make_ref(self, source_ref: str, url: str, **kwargs: object) -> ListingRef:
        return ListingRef(source_id=self.source.id, source_ref=source_ref, url=url, **kwargs)  # type: ignore[arg-type]
