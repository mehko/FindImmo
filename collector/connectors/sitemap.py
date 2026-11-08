"""Lecture de sitemaps XML (index récursifs, gzip) et connecteur générique « sitemap ».

Le ``SitemapConnector`` n'analyse pas les pages : il fournit la découverte. Les connecteurs
spécialisés (JSON-LD, HTML, adaptateurs) héritent de lui et implémentent ``parse_detail``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from lxml import etree

from ..geo import department_from_postal_code
from ..http import PoliteClient
from ..models import ListingRef
from .base import BaseConnector


class SitemapError(Exception):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(xml: str) -> tuple[str, list[tuple[str, str | None]]]:
    """Retourne (« index » | « urlset », [(loc, lastmod)])."""
    try:
        root = etree.fromstring(xml.encode("utf-8"), parser=etree.XMLParser(recover=True, huge_tree=True))
    except etree.XMLSyntaxError as exc:
        raise SitemapError(f"sitemap illisible : {exc}") from exc
    if root is None:
        raise SitemapError("sitemap vide ou illisible")
    kind = "index" if _local(root.tag) == "sitemapindex" else "urlset"
    entries: list[tuple[str, str | None]] = []
    for node in root:
        if _local(node.tag) not in ("url", "sitemap"):
            continue
        loc = lastmod = None
        for child in node:
            name = _local(child.tag)
            if name == "loc" and child.text:
                loc = child.text.strip()
            elif name == "lastmod" and child.text:
                lastmod = child.text.strip()
        if loc:
            entries.append((loc, lastmod))
    return kind, entries


def iter_sitemap(
    client: PoliteClient,
    url: str,
    include_sitemaps: str | None = None,
    max_depth: int = 3,
) -> Iterator[tuple[str, str | None]]:
    """Parcourt un sitemap (et ses sous-sitemaps filtrés par regex) et produit (loc, lastmod)."""
    kind, entries = parse_sitemap(client.get(url).text)
    if kind == "urlset":
        yield from entries
        return
    if max_depth <= 0:
        raise SitemapError(f"profondeur maximale atteinte : {url}")
    for loc, _ in entries:
        if include_sitemaps and not re.search(include_sitemaps, loc):
            continue
        yield from iter_sitemap(client, loc, include_sitemaps, max_depth - 1)


class SitemapConnector(BaseConnector):
    """Découverte par sitemap, configurée par ``options`` :

    * ``sitemaps`` : liste d'URL (défaut : sitemaps déclarés dans robots.txt) ;
    * ``include_sitemaps`` : regex des sous-sitemaps à suivre ;
    * ``url_pattern`` : regex appliquée aux URL ; groupes nommés ``ref`` (obligatoire),
      ``postal_code``, ``department``, ``city`` (slug), ``transaction`` (optionnels).
    """

    method = "sitemap"

    def sitemap_urls(self) -> list[str]:
        urls = self.options.get("sitemaps") or self.ctx.client.sitemaps(self.source.url)
        if not urls:
            raise SitemapError(f"aucun sitemap déclaré pour {self.source.id}")
        return list(urls)

    def ref_from_match(self, url: str, match: re.Match[str], lastmod: str | None) -> ListingRef | None:
        groups: dict[str, Any] = match.groupdict()
        postal = groups.get("postal_code")
        dep = groups.get("department") or department_from_postal_code(postal)
        if dep is None and groups.get("city"):
            communes = self.ctx.geo.communes_for_slug(groups["city"])
            deps = {c.department for c in communes}
            # Slug de commune présent dans plusieurs départements couverts : indéterminé.
            if len(deps) == 1:
                dep = deps.pop()
            elif not deps:
                dep = "hors-zone"
        return self.make_ref(
            groups["ref"], url, lastmod=lastmod, postal_code_hint=postal, department_hint=dep
        )

    def discover(self) -> Iterator[ListingRef]:
        pattern = re.compile(self.options["url_pattern"])
        seen: set[str] = set()
        for sm in self.sitemap_urls():
            for loc, lastmod in iter_sitemap(self.ctx.client, sm, self.options.get("include_sitemaps")):
                m = pattern.search(loc)
                if not m:
                    continue
                ref = self.ref_from_match(loc, m, lastmod)
                if ref is None or ref.source_ref in seen:
                    continue
                seen.add(ref.source_ref)
                yield ref
