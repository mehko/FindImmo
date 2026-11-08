"""Découverte et évaluation de domaines d'agences candidats.

Pour chaque domaine : robots.txt, sitemaps, empreinte du CMS, détection anti-bot, présence de
JSON-LD sur une page d'annonce échantillon. Le résultat est ajouté à
``config/sources.candidates.yaml`` avec ``enabled: false`` et ``compatibility: pending_validation``.
**Aucune source découverte n'est activée automatiquement** : l'activation est une décision humaine
(déplacer l'entrée dans ``sources.yaml`` et passer ``enabled: true``).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from .config import Settings, load_sources
from .connectors.jsonld import extract_jsonld, find_offer
from .connectors.sitemap import iter_sitemap
from .http import BlockedError, FetchError, PoliteClient
from .pipeline.tracker import now_iso

CMS_FINGERPRINTS = {
    "apimo": r"apimo",
    "hektor": r"hektor|la-boite-immo|laboiteimmo",
    "netty": r"netty\.fr|nettyimmo",
    "ubiflow": r"ubiflow",
    "immo-facile": r"immo-facile|immofacile",
    "adapt-immo": r"adaptimmo|adapt-immo",
    "ac3": r"\bac3\b|ac3-distribution",
    "wordpress": r"wp-content|wp-json",
    "laforet": r"laforet-intranet",
}
LISTING_URL_HINT = re.compile(r"/(annonces?|biens?|detail|vente|achat|location|property|listing)[/-]", re.I)


def probe(url: str, client: PoliteClient, max_sitemap_urls: int = 2000) -> dict[str, Any]:
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    result: dict[str, Any] = {"url": base, "domain": parts.netloc, "checked_at": now_iso(), "issues": []}
    try:
        result["robots_allows_home"] = client.allowed(base + "/")
        result["sitemaps"] = client.sitemaps(base)
        home = client.get(base + "/").text
    except BlockedError as exc:
        result["compatibility"] = "blocked"
        result["issues"].append(str(exc))
        return result
    except FetchError as exc:
        result["compatibility"] = "incompatible"
        result["issues"].append(str(exc))
        return result
    result["cms"] = next((name for name, rx in CMS_FINGERPRINTS.items() if re.search(rx, home, re.I)), None)

    sample_urls: list[str] = []
    for sm in result["sitemaps"][:3] or [base + "/sitemap.xml"]:
        try:
            for loc, _ in iter_sitemap(client, sm, max_depth=2):
                if LISTING_URL_HINT.search(loc):
                    sample_urls.append(loc)
                if len(sample_urls) >= max_sitemap_urls:
                    break
        except Exception as exc:  # noqa: BLE001
            result["issues"].append(f"sitemap {sm} : {exc}")
    result["listing_like_urls"] = len(sample_urls)

    has_jsonld = False
    for sample in sample_urls[-3:]:
        if not client.allowed(sample):
            result["issues"].append(f"robots.txt interdit {sample}")
            continue
        try:
            _l, offer, item = find_offer(extract_jsonld(client.get(sample).text))
        except FetchError as exc:
            result["issues"].append(str(exc))
            continue
        if offer or item:
            has_jsonld = True
            result["sample_listing"] = sample
            break
    result["jsonld_listing"] = has_jsonld
    if not result["robots_allows_home"]:
        result["compatibility"] = "blocked"
    elif has_jsonld:
        result["compatibility"] = "pending_validation"
        result["suggested_method"] = "sitemap_jsonld"
    else:
        result["compatibility"] = "pending_validation"
        result["suggested_method"] = "html"
        result["issues"].append("pas de JSON-LD : sélecteurs HTML à définir manuellement")
    return result


def discover_candidates(urls: list[str], settings: Settings, config_dir: Path) -> list[dict[str, Any]]:
    client = PoliteClient(settings.user_agent)
    known = {s.domain.removeprefix("www.") for s in load_sources(config_dir, include_candidates=True)}
    results = []
    try:
        for url in urls:
            domain = urlsplit(url if "://" in url else "https://" + url).netloc
            if domain.removeprefix("www.") in known:
                results.append({"domain": domain, "skipped": "déjà enregistré"})
                continue
            results.append(probe(url, client))
    finally:
        client.close()

    path = config_dir / "sources.candidates.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    data = data or {"sources": []}
    for r in results:
        if "skipped" in r:
            continue
        sid = re.sub(r"[^a-z0-9]+", "-", r["domain"].removeprefix("www.").rsplit(".", 1)[0]).strip("-")
        data["sources"].append(
            {
                "id": sid,
                "name": r["domain"],
                "domain": r["domain"],
                "url": r["url"],
                "cms": r.get("cms"),
                "method": r.get("suggested_method", "html"),
                "enabled": False,
                "compatibility": r["compatibility"],
                "options": {"sitemaps": r.get("sitemaps", [])},
                "notes": "; ".join(r["issues"])[:500] or f"évalué le {r['checked_at']}",
            }
        )
    path.write_text(
        "# Sources découvertes, en attente de validation. NE PAS activer sans vérification manuelle.\n"
        + yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return results
