import json
import re

import pytest

from collector.connectors.adapters.era import EraConnector
from collector.connectors.adapters.foncia import FonciaConnector
from collector.connectors.adapters.hektor import HektorConnector
from collector.connectors.adapters.human import HumanConnector
from collector.connectors.adapters.laforet import LaforetConnector
from collector.connectors.feed import FeedConnector
from collector.connectors.html import HtmlConnector
from collector.connectors.jsonld import JsonLdConnector, extract_jsonld, find_offer, raw_from_jsonld
from collector.connectors.registry import build_connector
from collector.connectors.sitemap import iter_sitemap, parse_sitemap
from collector.http import ListingRemoved
from collector.models import ListingRef

from .conftest import FIXTURES, FakeSite, fixture, make_ctx, make_source

SITEMAP_INDEX = """<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://agence-test.example/sitemap-annonces.xml</loc></sitemap>
<sitemap><loc>https://agence-test.example/sitemap-blog.xml</loc></sitemap></sitemapindex>"""
SITEMAP_URLS = """<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://agence-test.example/annonces/vente/maison/fontainebleau-77300/TMAI100</loc><lastmod>2026-11-01</lastmod></url>
<url><loc>https://agence-test.example/annonces/vente/maison/lyon-69003/TMAI200</loc></url>
<url><loc>https://agence-test.example/annonces/vente</loc></url>
</urlset>"""
PATTERN = r"/annonces/(?:vente|location)/[^/]+/[^/]+-(?P<postal_code>\d{5})/(?P<ref>[A-Z0-9]+)$"


def test_parse_sitemap_index_and_urlset():
    kind, entries = parse_sitemap(SITEMAP_INDEX)
    assert kind == "index" and len(entries) == 2
    kind, entries = parse_sitemap(SITEMAP_URLS)
    assert kind == "urlset" and entries[0][1] == "2026-11-01"


def test_iter_sitemap_follows_filtered_children():
    site = FakeSite({
        "https://agence-test.example/sitemap.xml": SITEMAP_INDEX,
        "https://agence-test.example/sitemap-annonces.xml": SITEMAP_URLS,
    })
    locs = [loc for loc, _ in iter_sitemap(site.client(), "https://agence-test.example/sitemap.xml", "annonces")]
    assert len(locs) == 3
    assert "https://agence-test.example/sitemap-blog.xml" not in site.hits


def test_jsonld_connector_discovery_prefilters_by_postal_code(geo, departments):
    site = FakeSite({
        "https://agence-test.example/sitemap.xml": SITEMAP_INDEX,
        "https://agence-test.example/sitemap-annonces.xml": SITEMAP_URLS,
    })
    src = make_source(options={"sitemaps": ["https://agence-test.example/sitemap.xml"], "include_sitemaps": "annonces",
                               "url_pattern": PATTERN})
    conn = JsonLdConnector(src, make_ctx(site.client(), geo, departments))
    refs = list(conn.discover())
    assert [r.source_ref for r in refs] == ["TMAI100", "TMAI200"]
    assert [conn.ref_in_scope(r) for r in refs] == [True, False]
    assert refs[0].lastmod == "2026-11-01"


def test_jsonld_real_estate_listing_extraction():
    raw = raw_from_jsonld(extract_jsonld(fixture("jsonld_listing.html")), "test", "TMAI100", "https://x")
    assert raw is not None
    assert raw.transaction == "sale" and raw.property_type == "house"
    assert raw.price == 480000 and raw.surface == 120 and raw.rooms == 5
    assert raw.postal_code == "77300" and raw.city == "Fontainebleau"
    assert (raw.latitude, raw.longitude) == (48.404, 2.701)
    assert raw.dpe == "C" and raw.ges == "B"
    assert raw.features == {"parking": True, "cellar": False, "pool": False}
    assert raw.published_at == "2026-10-30"


def test_jsonld_graph_and_rent_offer():
    raw = raw_from_jsonld(extract_jsonld(fixture("jsonld_graph.html")), "test", "A1", "https://x/a1")
    assert raw is not None
    assert raw.transaction == "rent" and raw.property_type == "apartment"
    assert raw.price == 1250 and raw.rooms == 2
    assert raw.surface == 45 and "surface" in raw.parsed_fields  # lu dans le nom


def test_jsonld_graph_with_id_references_and_transaction_from_title(geo, departments):
    """Graphe où l'offre pointe le bien par ``@id`` (structure observée chez Century 21)."""
    html = (
        '<html><head><script type="application/ld+json">{"@context":"https://schema.org","@graph":['
        '{"@type":"WebPage","@id":"https://x/d/1/#webpage","mainEntity":{"@id":"https://x/d/1/#offer"}},'
        '{"@type":"Offer","@id":"https://x/d/1/#offer","price":245000,"itemOffered":{"@id":"https://x/d/1/#property"}},'
        '{"@type":"Apartment","@id":"https://x/d/1/#property","name":"Appartement F2 à vendre - 2 pièces - 47.63 m2 - COLOMBES",'
        '"numberOfRooms":2,"floorSize":{"@type":"QuantitativeValue","value":48},'
        '"address":{"@type":"PostalAddress","addressLocality":"COLOMBES","postalCode":"92700"}}'
        "]}</script></head><body></body></html>"
    )
    src = make_source(options={"transaction_from_title": {"à vendre": "sale", "à louer": "rent"}})
    conn = JsonLdConnector(src, make_ctx(FakeSite().client(), geo, departments))
    raw = conn.parse_detail(html, ListingRef(source_id="test", source_ref="1", url="https://x/d/1/"))
    assert raw is not None
    assert (raw.price, raw.surface, raw.rooms, raw.postal_code, raw.city) == (245000, 48, 2, "92700", "COLOMBES")
    assert raw.property_type == "apartment" and raw.transaction == "sale"


def test_jsonld_fallback_fields_when_no_structured_data(geo, departments):
    html = ('<html><head><meta property="og:title" content="Parking à vendre 12 m² - Toulon (83) - 29 000€">'
            '</head><body><div data-latitude="43.12" data-longitude="5.95"></div></body></html>')
    src = make_source(options={"fallback_fields": {
        "title": {"selector": "meta[property='og:title']", "attr": "content"},
        "price": {"selector": "meta[property='og:title']", "attr": "content", "regex": r"- ([\d\s ]+)€"},
        "city": {"selector": "meta[property='og:title']", "attr": "content", "regex": r"- ([^-]+?) \(\d{2,3}\)"},
        "latitude": {"selector": "[data-latitude]", "attr": "data-latitude"},
    }, "transaction_from_url": {"/vente/": "sale"}})
    conn = JsonLdConnector(src, make_ctx(FakeSite().client(), geo, departments))
    raw = conn.parse_detail(html, ListingRef(source_id="test", source_ref="P1", url="https://x/vente/p1", postal_code_hint="83137"))
    assert raw is not None
    assert (raw.price, raw.surface, raw.city, raw.latitude, raw.transaction) == (29000, 12, "Toulon", 43.12, "sale")
    assert {"price", "surface", "city"} <= set(raw.parsed_fields)


def test_laforet_adapter_detail(geo, departments):
    src = make_source(id="laforet", method="adapter", adapter="laforet")
    conn = build_connector(src, make_ctx(FakeSite().client(), geo, departments))
    assert isinstance(conn, LaforetConnector)
    url = "https://www.laforet.com/agence-immobiliere/levesinet/acheter/le-vesinet/maison-6-pieces-53000001"
    raw = conn.parse_detail(fixture("laforet_detail.html"), ListingRef(source_id="laforet", source_ref="53000001", url=url))
    assert raw is not None
    assert raw.transaction == "sale" and raw.property_type == "house"
    assert (raw.price, raw.surface, raw.rooms, raw.bedrooms, raw.land_surface) == (950000, 140, 6, 4, 820)
    assert raw.postal_code == "78110" and raw.city == "LE VESINET"
    assert raw.features == {"pool": True, "garage": True, "terrace": True}  # les « false » sont ignorés
    assert raw.latitude == 48.8931 and raw.agency == "Laforêt Test"
    assert raw.dpe is None  # DPE uniquement en image : jamais deviné


def test_laforet_discovery_uses_city_slug(geo, departments):
    sm = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://www.laforet.com/agence-immobiliere/levesinet/acheter/chatou/maison-7-pieces-53018036</loc></url>
    <url><loc>https://www.laforet.com/agence-immobiliere/lyon/acheter/villeurbanne/appartement-2-pieces-1</loc></url>
    <url><loc>https://www.laforet.com/agence-immobiliere/paris11/louer/paris-11/appartement-2-pieces-2</loc></url>
    </urlset>"""
    site = FakeSite({"https://www.laforet.com/storage/sitemaps/produits.xml": sm})
    conn = LaforetConnector(make_source(id="laforet", method="adapter", adapter="laforet"), make_ctx(site.client(), geo, departments))
    refs = list(conn.discover())
    assert [(r.source_ref, r.department_hint) for r in refs] == [("53018036", "78"), ("1", "hors-zone"), ("2", "75")]
    assert [conn.ref_in_scope(r) for r in refs] == [True, False, True]


def test_html_connector_list_pages_and_selectors(geo, departments):
    site = FakeSite({
        "https://agence-html.example/vente.html": fixture("html_list.html"),
        "https://agence-html.example/vente/villa-hyeres-42.html": fixture("html_detail.html"),
    })
    src = make_source(id="html", method="html", domain="agence-html.example", url="https://agence-html.example", options={
        "list_pages": ["https://agence-html.example/vente.html"],
        "url_pattern": r"/vente/[a-z-]+-(?P<ref>\d+)\.html$",
        "transaction_from_url": {"/vente/": "sale"},
        "fields": {
            "title": "h1.titre", "price": ".prix", "surface": ".surface", "city": {"selector": ".ville", "regex": r"^([^(]+)"},
            "postal_code": {"selector": ".ville", "regex": r"(\d{5})"}, "description": ".description",
            "image": {"selector": "meta[property='og:image']", "attr": "content"},
        },
        "features_selector": ".equipements li",
    })
    conn = HtmlConnector(src, make_ctx(site.client(), geo, departments))
    refs = list(conn.discover())
    assert [r.source_ref for r in refs] == ["42", "43"]
    raw = conn.fetch_detail(refs[0])
    assert raw is not None
    assert (raw.price, raw.surface, raw.city, raw.postal_code) == (785000, 110.5, "Hyères", "83400")
    assert (raw.rooms, raw.bedrooms, raw.land_surface, raw.dpe, raw.transaction) == (4, 3, 1200, "B", "sale")
    assert raw.features == {"pool": True, "garage": True}  # « Sans ascenseur » n'est pas une mention positive
    assert "features.pool" in raw.parsed_fields


def test_feed_connector_mapping(geo, departments):
    src = make_source(id="feed", method="feed", options={
        "feed_url": f"file://{FIXTURES / 'feed.json'}", "items_path": "data.listings",
        "mapping": {"source_ref": "id", "url": "lien", "price": "prix", "city": "ville", "postal_code": "cp",
                    "property_type": "type", "rooms": "pieces"},
    })
    conn = FeedConnector(src, make_ctx(FakeSite().client(), geo, departments))
    refs = list(conn.discover())
    assert [r.source_ref for r in refs] == ["501", "502"]  # l'élément sans URL est ignoré
    assert refs[0].raw is not None and refs[0].raw.postal_code == "83000"
    assert conn.fetch_detail(refs[1]) is refs[1].raw
    json.dumps([r.model_dump() for r in refs])


def test_human_adapter_discovery_paginates_and_stops_on_redirect(geo, departments):
    base = "https://www.human.example/achat-immobilier-ville-test"
    page2 = fixture("human_list.html").replace("ville-test_900-1001", "ville-test_900-1003").replace(
        "ville-test_900-1002", "ville-test_900-1004")
    site = FakeSite({
        base: fixture("human_list.html"),
        base + "?page=2": page2,
        base + "?page=3": (302, "https://www.human.example/acheter/annonces-immobilieres-achat"),
        "https://www.human.example/acheter/annonces-immobilieres-achat": "<html>recherche nationale</html>",
    })
    src = make_source(id="human", method="adapter", adapter="human", domain="www.human.example",
                      url="https://www.human.example",
                      options={"list_pages": [base], "cities": ["ville-test"], "max_pages": 5})
    conn = build_connector(src, make_ctx(site.client(), geo, departments))
    assert isinstance(conn, HumanConnector)
    refs = list(conn.discover())
    assert [r.source_ref for r in refs] == ["900-1001", "900-1002", "900-1003", "900-1004"]  # sans doublon ni hors commune
    assert refs[0].url == "https://www.human.example/annonce-achat-appartement-ville-test_900-1001"


def test_human_adapter_detail_and_sold(geo, departments):
    src = make_source(id="human", method="adapter", adapter="human", options={})
    conn = build_connector(src, make_ctx(FakeSite().client(), geo, departments))
    url = "https://www.human.example/annonce-achat-appartement-ville-test_900-1001"
    ref = ListingRef(source_id="human", source_ref="900-1001", url=url)
    raw = conn.parse_detail(fixture("human_detail.html"), ref)
    assert raw is not None
    assert raw.transaction == "sale" and raw.property_type == "apartment"
    assert (raw.price, raw.surface, raw.rooms, raw.bedrooms) == (310000, 58.2, 3, 2)
    assert (raw.postal_code, raw.dpe, raw.ges) == ("92000", "D", "B")
    assert "é" in raw.description and "&#x" not in raw.description  # entités HTML décodées
    assert raw.features == {"terrace": True, "cellar": True}
    assert raw.latitude is None  # coordonnées de la page = agence, non reprises
    with pytest.raises(ListingRemoved):
        conn.parse_detail(fixture("human_detail_sold.html"), ref)


def _remax_connector(geo, departments, site=None, **options):
    src = make_source(id="remax", method="adapter", adapter="remax", domain="remax.example",
                      url="https://remax.example", options=options)
    return build_connector(src, make_ctx((site or FakeSite()).client(), geo, departments))


def test_remax_adapter_discovery_targets_listing_sitemap_and_prefilters(geo, departments):
    index = ('<?xml version="1.0"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
             "<sitemap><loc>https://remax.example/sitemap/listings_details_fr_1.xml.gz</loc></sitemap>"
             "<sitemap><loc>https://remax.example/sitemap/listings_search_buy_fr_01.xml.gz</loc></sitemap></sitemapindex>")
    details = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
               "<url><loc>https://remax.example/fr/900000001-11</loc></url>"  # forme courte : ignorée
               "<url><loc>https://remax.example/fr/mandats/vente-appartement-ch2-hauts-de-seine---92-ville-test/900000001-11</loc></url>"
               "<url><loc>https://remax.example/fr/mandats/location-maison-ch3-haute-savoie---74-arthaz-pont-notre-dame/900000002-22</loc></url>"
               "</urlset>")
    site = FakeSite({
        "https://remax.example/sitemap.xml": index,
        "https://remax.example/sitemap/listings_details_fr_1.xml.gz": details,
        # le sitemap de recherche ne doit jamais être téléchargé : absent de FakeSite → 404 si demandé
    })
    conn = _remax_connector(geo, departments, site, sitemaps=["https://remax.example/sitemap.xml"])
    refs = list(conn.discover())
    assert [r.source_ref for r in refs] == ["900000001-11", "900000002-22"]
    assert [r.department_hint for r in refs] == ["92", "74"]
    assert conn.ref_in_scope(refs[0]) is True and conn.ref_in_scope(refs[1]) is False
    assert not any("search" in u for u in site.hits)


def test_remax_adapter_detail_sold_and_rent(geo, departments):
    conn = _remax_connector(geo, departments)
    sale_url = "https://remax.example/fr/mandats/vente-appartement-ch2-hauts-de-seine---92-ville-test/900000001-11"
    ref = ListingRef(source_id="remax", source_ref="900000001-11", url=sale_url)
    raw = conn.parse_detail(fixture("remax_detail.html"), ref)
    assert raw is not None
    assert raw.transaction == "sale" and raw.property_type == "apartment"
    assert (raw.price, raw.surface, raw.rooms, raw.bedrooms) == (310000, 58.5, 3, 2)
    assert (raw.postal_code, raw.city, raw.dpe, raw.ges) == ("92000", "Ville-Test", "D", None)  # niveau 14 = non renseigné
    assert raw.features == {"parking": True, "elevator": True}
    assert raw.description == "Bel appartement lumineux. Proche transports."
    assert raw.title == "Appartement à vendre - Ville-Test, Hauts-de-Seine - 92"
    assert raw.image == "https://i.maxwork.fr/ds-l/listings/90000/1/photo.jpg" and raw.published_at == "2026-10-01"
    assert raw.agency == "RE/MAX AGENCE FICTIVE"
    assert raw.latitude is None  # adresse non exacte : coordonnées approximatives ignorées

    with pytest.raises(ListingRemoved):
        conn.parse_detail(fixture("remax_detail_sold.html"), ref)

    rent_url = "https://remax.example/fr/mandats/location-appartement-ch1-hauts-de-seine---92-ville-test/900000001-12"
    rent = conn.parse_detail(fixture("remax_detail_rent.html"), ListingRef(source_id="remax", source_ref="900000001-12", url=rent_url))
    assert rent.transaction == "rent" and rent.price == 995
    assert (rent.latitude, rent.longitude) == (48.9, 2.25)  # adresse exacte : coordonnées reprises
    assert conn.parse_detail("<html></html>", ref) is None  # page sans __NEXT_DATA__


def test_jsonld_listing_with_property_in_about_apimo_variant(geo, departments):
    """Plateformes Apimo : RealEstateListing avec le bien dans « about » et l'offre dans « offers »."""
    raw = raw_from_jsonld(extract_jsonld(fixture("jsonld_apimo.html")), "test", "9000001", "https://x")
    assert raw is not None
    assert raw.property_type == "house" and raw.price == 755000
    assert (raw.surface, raw.rooms, raw.bedrooms) == (96, 4, 3)
    assert (raw.city, raw.postal_code, raw.latitude) == ("Ville-Test", "92000", 48.9)


def test_jsonld_connector_default_transaction_url_type_and_removed_markers(geo, departments):
    src = make_source(options={"default_transaction": "sale", "removed_markers": [r"^\s*VENDU"],
                               "property_type_from_url": {"+garage-parking+": "parking"}})
    conn = JsonLdConnector(src, make_ctx(FakeSite().client(), geo, departments))
    url = "https://agence.example/fr/propriete/vente+maison+ville-test+maison-4p+9000001"
    raw = conn.parse_detail(fixture("jsonld_apimo.html"), ListingRef(source_id="test", source_ref="9000001", url=url))
    assert raw.transaction == "sale" and raw.property_type == "house"  # le type JSON-LD prime sur l'URL
    sold_url = url.replace("vente+maison+", "vente+garage-parking+")
    with pytest.raises(ListingRemoved):
        conn.parse_detail(fixture("jsonld_apimo_sold.html"), ListingRef(source_id="test", source_ref="9000001", url=sold_url))


def test_html_connector_og_title_configuration_of_arthurimmo(geo, departments):
    """La configuration réelle de la source `arthurimmo-colombes` doit extraire une annonce fictive de même forme."""
    from collector.config import load_sources

    cfg = next(s for s in load_sources() if s.id == "arthurimmo-colombes")
    conn = HtmlConnector(cfg, make_ctx(FakeSite().client(), geo, departments))
    url = "https://colombes.example/annonces/achat/appartement/ville-test-92000/1.htm"
    raw = conn.parse_detail(fixture("html_og_listing.html"), ListingRef(source_id=cfg.id, source_ref="1", url=url))
    assert raw is not None
    assert (raw.transaction, raw.property_type) == ("sale", "appartement")
    assert (raw.price, raw.surface, raw.rooms, raw.bedrooms) == (340000, 77, 4, 2)
    assert (raw.city, raw.postal_code) == ("Ville-Test", "92000")
    assert raw.image == "https://media.example/biens/1/photo"
    # La découverte retient une URL d'annonce et pré-filtre par code postal.
    m = re.search(cfg.options["url_pattern"], url)
    assert m and m["postal_code"] == "92000" and m["ref"] == "1"


def test_html_connector_houzez_configuration_of_lesagentsdelimmobilier(geo, departments):
    """Configuration réelle de `lesagentsdelimmobilier` (thème Houzez) sur une page fictive de même structure."""
    from collector.config import load_sources

    cfg = next(s for s in load_sources() if s.id == "lesagentsdelimmobilier")
    conn = HtmlConnector(cfg, make_ctx(FakeSite().client(), geo, departments))
    url = "https://agence.example/annonces/appartement-3-pieces-ville-test/"
    raw = conn.parse_detail(fixture("html_houzez_detail.html"), ListingRef(source_id=cfg.id, source_ref="x", url=url))
    assert raw is not None
    assert (raw.transaction, raw.property_type) == ("acheter", "APPARTEMENT")  # normalisés par le pipeline
    assert (raw.price, raw.surface, raw.rooms, raw.bedrooms) == (272000, 47, 3, 1)
    assert (raw.city, raw.postal_code, raw.dpe) == ("VILLE-TEST", "92000", "E")
    m = re.search(cfg.options["url_pattern"], url)
    assert m and m["ref"] == "appartement-3-pieces-ville-test"


def _era_connector(geo, departments, site=None, **options):
    base = "https://www.era.example/achat/idf-1/hauts-de-seine-97"
    src = make_source(id="era", method="adapter", adapter="era", domain="www.era.example", url="https://www.era.example",
                      options={"list_pages": [base], **options})
    return base, build_connector(src, make_ctx((site or FakeSite()).client(), geo, departments))


def test_era_adapter_discovery_reads_embedded_search_and_stops_at_total(geo, departments):
    base = "https://www.era.example/achat/idf-1/hauts-de-seine-97"
    site = FakeSite({base: fixture("era_list_page1.html"), base + "?page=2": fixture("era_list_page2.html")})
    _, conn = _era_connector(geo, departments, site)
    assert isinstance(conn, EraConnector)
    refs = list(conn.discover())
    # 3 annonces au total, 2 par page : la page 3 n'est jamais demandée ; l'annonce 1002 (en double) est dédupliquée.
    assert [r.source_ref for r in refs] == ["1001", "1002", "1003"]
    assert not any(u.endswith("page=3") for u in site.hits)
    assert all(r.raw is not None and r.postal_code_hint == "92000" for r in refs)
    assert conn.fetch_detail(refs[0]) is refs[0].raw  # aucune page détail à télécharger


def test_era_adapter_item_mapping_and_failure_on_unexpected_page(geo, departments):
    base = "https://www.era.example/achat/idf-1/hauts-de-seine-97"
    site = FakeSite({base: fixture("era_list_page1.html"), base + "?page=2": fixture("era_list_page2.html")})
    _, conn = _era_connector(geo, departments, site)
    sale, rent, house = (r.raw for r in conn.discover())
    assert (sale.transaction, sale.property_type, sale.price, sale.surface) == ("Vente", "Appartement", 310000, 58)
    assert (sale.rooms, sale.bedrooms, sale.city, sale.postal_code) == (3, 2, "ville-test", "92000")
    assert (sale.dpe, sale.ges, sale.agency) == ("D", None, "ERA AGENCE FICTIVE")
    assert sale.features == {"elevator": True, "cellar": True, "parking": True}  # les critères à 0 sont ignorés
    assert sale.description == "Bel appartement lumineux. Proche transports."  # HTML retiré, ponctuation recollée
    assert sale.image == "https://img.example/a.jpg" and sale.published_at == "2026-10-01"
    assert sale.url == "https://www.eraimmobilier.com/annonces/1001" and sale.latitude is None  # GPS = centre de commune
    assert (rent.transaction, rent.price, rent.surface, rent.dpe) == ("Location", 995, None, None)  # 0 → inconnu ; « Vierge » ignoré
    assert (house.land_surface, house.bedrooms) == (250, None)

    broken = FakeSite({base: "<html><body>maintenance</body></html>"})
    _, conn2 = _era_connector(geo, departments, broken)
    with pytest.raises(ValueError):
        list(conn2.discover())  # structure inattendue : la découverte ne doit pas passer pour exhaustive


def test_jsonld_netty_product_with_item_offered_and_schemeless_offer_url(geo, departments):
    """Netty : Product enveloppant offers.itemOffered ; l'URL de l'offre n'a pas de schéma."""
    page_url = "https://www.agence.example/vente/appartement-t3-3-pieces-ville-test-92000,VA1994"
    raw = raw_from_jsonld(extract_jsonld(fixture("jsonld_netty.html")), "test", "VA1994", page_url)
    assert raw is not None
    assert (raw.property_type, raw.price, raw.surface, raw.rooms) == ("apartment", 275000, 60, 3)
    assert (raw.city, raw.postal_code) == ("VILLE-TEST", "92000")
    assert raw.url == page_url  # « www.agence.example/… » (sans schéma) n'est pas repris
    assert raw.image == "https://img.example/product/VA1994/photo1.jpg"  # image de l'enveloppe Product


def test_jsonld_netty_sold_listing_has_zero_price_and_is_removed(geo, departments):
    src = make_source(options={"removed_if_no_price": True})
    conn = JsonLdConnector(src, make_ctx(FakeSite().client(), geo, departments))
    url = "https://www.agence.example/vente/appartement-t3-3-pieces-ville-test-92000,VA1994"
    ref = ListingRef(source_id="test", source_ref="VA1994", url=url)
    assert conn.parse_detail(fixture("jsonld_netty.html"), ref).price == 275000
    with pytest.raises(ListingRemoved):
        conn.parse_detail(fixture("jsonld_netty.html").replace('"price":275000', '"price":0'), ref)
    # Sans l'option, un prix absent n'est pas une raison de retirer l'annonce.
    plain = JsonLdConnector(make_source(), make_ctx(FakeSite().client(), geo, departments))
    assert plain.parse_detail(fixture("jsonld_netty.html").replace('"price":275000', '"price":0'), ref).price is None


def _hektor(geo, departments, source_id):
    from collector.config import load_sources

    cfg = next(s for s in load_sources() if s.id == source_id)
    assert cfg.adapter == "hektor"
    return cfg, build_connector(cfg, make_ctx(FakeSite().client(), geo, departments))


def test_hektor_act_immo_theme_and_derived_buyer_price(geo, departments):
    cfg, conn = _hektor(geo, departments, "act-immo")
    assert isinstance(conn, HektorConnector)
    url = "https://www.act-immo.net/vente/1-ville-test/maison/945-ville-test-maison-6-pieces"
    ref = ListingRef(source_id=cfg.id, source_ref="945", url=url)
    m = re.search(cfg.options["url_pattern"], url)
    assert m and (m["transaction"], m["city"], m["type"], m["ref"]) == ("vente", "ville-test", "maison", "945")

    # Prix du bandeau vide : prix net vendeur 680 000 € × (1 + 2,65 %) = 698 020 € → arrondi à 100 €.
    raw = conn.parse_detail(fixture("hektor_act_house.html"), ref)
    assert raw is not None
    assert (raw.property_type, raw.surface, raw.rooms, raw.bedrooms) == ("Maison", 92, 6, 3)
    assert (raw.city, raw.postal_code, raw.transaction) == ("Ville-Test", "92000", "sale")
    assert raw.price == 698000 and "price" in raw.parsed_fields
    assert raw.image == "https://agence.staticlbi.com/photo.jpg"  # URL sans schéma complétée

    # Prix du bandeau renseigné : jamais écrasé, non marqué « parsed ».
    priced = conn.parse_detail(fixture("hektor_act_priced.html"), ref)
    assert priced.price == 295000 and "price" not in priced.parsed_fields

    # Sans taux d'honoraires lisible : on ne publie pas le prix net vendeur comme prix d'achat.
    assert conn.parse_detail(fixture("hektor_act_norate.html"), ref).price is None


def test_hektor_coeuret_theme(geo, departments):
    cfg, conn = _hektor(geo, departments, "coeuretimmobilier")
    url = "https://www.coeuretimmobilier.com/vente/1-ville-test/maison/348-maison-familiale"
    raw = conn.parse_detail(fixture("hektor_coeuret.html"), ListingRef(source_id=cfg.id, source_ref="348", url=url))
    assert raw is not None
    assert (raw.property_type, raw.price, raw.surface, raw.rooms, raw.bedrooms) == ("Maison", 440000, 81.13, 5, 3)
    assert (raw.city, raw.postal_code, raw.transaction) == ("Ville-Test", "92000", "sale")


def test_foncia_adapter_discovery_prefilters_by_postal_code_or_department(geo, departments):
    sale = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://fr.example/achat/ville-test-92000/appartement/00000001.htm</loc></url>"
            "<url><loc>https://fr.example/achat/paris-75/appartement/00000002.htm</loc></url>"  # département seul (ville multi-codes)
            "<url><loc>https://fr.example/achat/lyon-69003/appartement/00000003.htm</loc></url>"
            "<url><loc>https://fr.example/achat/colombes-92700</loc></url></urlset>")  # page de liste : ignorée
    rent = ('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://fr.example/location/orly-94310/appartement-meuble/331700001.htm</loc></url></urlset>")
    site = FakeSite({"https://fr.example/achat-annonce.xml": sale, "https://fr.example/location-annonce.xml": rent})
    src = make_source(id="foncia", method="adapter", adapter="foncia", domain="fr.example", url="https://fr.example",
                      options={"sitemaps": ["https://fr.example/achat-annonce.xml", "https://fr.example/location-annonce.xml"]})
    conn = build_connector(src, make_ctx(site.client(), geo, {"92"}))
    assert isinstance(conn, FonciaConnector)
    refs = list(conn.discover())
    assert [r.source_ref for r in refs] == ["00000001", "00000002", "00000003", "331700001"]
    assert [(r.postal_code_hint, r.department_hint) for r in refs][:2] == [("92000", "92"), (None, "75")]
    assert [conn.ref_in_scope(r) for r in refs] == [True, False, False, False]  # seul le 92 est dans la zone


def test_foncia_adapter_detail_sale_rent_and_inactive(geo, departments):
    src = make_source(id="foncia", method="adapter", adapter="foncia", options={})
    conn = build_connector(src, make_ctx(FakeSite().client(), geo, departments))
    sale_url = "https://fr.example/achat/ville-test-92000/appartement/00000001.htm"
    raw = conn.parse_detail(fixture("foncia_sale.html"), ListingRef(source_id="foncia", source_ref="00000001", url=sale_url))
    assert raw is not None
    assert (raw.transaction, raw.property_type, raw.price) == ("sale", "apartment", 186000)
    assert (raw.surface, raw.rooms, raw.city, raw.postal_code) == (36.5, 2, "Ville-Test", "92000")
    assert (raw.dpe, raw.ges) == ("C", None)  # lettre invalide (« Z ») ignorée
    assert raw.features == {"elevator": True, "cellar": True}  # « available: False » ignoré
    assert raw.description == "Bel appartement d'angle. Proche transports."  # échappements Angular décodés
    assert raw.published_at == "2026-07-24" and raw.image == "https://img.example/foncia/lg.jpeg"
    assert raw.latitude is None  # précision des coordonnées non documentée

    rent_url = "https://fr.example/location/ville-test-92000/appartement-meuble/331700001.htm"
    rent = conn.parse_detail(fixture("foncia_rent.html"), ListingRef(source_id="foncia", source_ref="331700001", url=rent_url))
    assert (rent.transaction, rent.price, rent.surface, rent.rooms, rent.dpe) == ("rent", 1300, 58.38, 3, None)
    assert rent.features.get("furnished") is True  # type d'URL « appartement-meuble »

    with pytest.raises(ListingRemoved):
        conn.parse_detail(fixture("foncia_deleted.html"), ListingRef(source_id="foncia", source_ref="00000001", url=sale_url))
    assert conn.parse_detail("<html></html>", ListingRef(source_id="foncia", source_ref="x", url=sale_url)) is None


def _source(source_id, geo, departments):
    from collector.config import load_sources

    cfg = next(s for s in load_sources() if s.id == source_id)
    return cfg, build_connector(cfg, make_ctx(FakeSite().client(), geo, departments))


def test_asm_json_ld_without_price_is_completed_from_html(geo, departments):
    cfg, conn = _source("asm-immobilier", geo, departments)
    url = "https://asm.example/bien/3-pieces-fictif/"
    ref = ListingRef(source_id=cfg.id, source_ref="3-pieces-fictif", url=url)
    assert re.search(cfg.options["url_pattern"], url) and not re.search(cfg.options["url_pattern"], "https://asm.example/bien/")

    raw = conn.parse_detail(fixture("asm_active.html"), ref)  # contient une étiquette « Vendu » de fiche SIMILAIRE
    assert raw is not None
    # JSON-LD prioritaire : surface, commune et CP DU BIEN (le 92400 de l'agence n'est pas repris par erreur).
    assert (raw.surface, raw.city, raw.postal_code) == (71.1, "Courbevoie", "92400")
    # Champs absents du JSON-LD lus dans le HTML, et marqués comme tels.
    assert (raw.price, raw.rooms, raw.property_type, raw.transaction) == (590000, 3, "Appartement", "A vendre")
    assert {"price", "rooms", "property_type", "transaction"} <= set(raw.parsed_fields)
    assert "surface" not in raw.parsed_fields

    rent = conn.parse_detail(fixture("asm_rent.html"), ref)
    assert (rent.price, rent.transaction) == (1590, "A louer")

    for sold in ("asm_sold_statut.html", "asm_sold_crumb.html"):  # statut du bien OU fil d'Ariane
        with pytest.raises(ListingRemoved):
            conn.parse_detail(fixture(sold), ref)


def test_find_offer_prefers_richest_real_estate_listing_and_normalizes_a_vendre():
    from collector.models import TransactionType
    from collector.pipeline.normalize import TRANSACTION_SYNONYMS, _map

    listing, offer, item = find_offer(extract_jsonld(fixture("asm_active.html")))
    assert offer is None and item is listing and "floorSize" in item  # fiche détaillée choisie, pas l'enveloppe WebPage
    assert _map("A vendre", TRANSACTION_SYNONYMS) == TransactionType.SALE
    assert _map("A louer", TRANSACTION_SYNONYMS) == TransactionType.RENT


def test_gridimmo_configuration_sale_and_rent(geo, departments):
    cfg, conn = _source("gridimmo", geo, departments)
    url = "https://www.gridimmo.fr/fr/annonces-immobilieres/offre/ville-test/bien/3609/f4-centre-ville.html"
    m = re.search(cfg.options["url_pattern"], url)
    assert m and (m["city"], m["ref"]) == ("ville-test", "3609")
    assert not re.search(cfg.options["url_pattern"], url.replace("/fr/annonces-immobilieres/offre/", "/en/realestate-adverts/offer/"))

    sale = conn.parse_detail(fixture("gridimmo_sale.html"), ListingRef(source_id=cfg.id, source_ref="3609", url=url))
    assert (sale.transaction, sale.property_type, sale.city) == ("sale", "Appartement", "Ville-Test")
    assert (sale.price, sale.rooms, sale.bedrooms, sale.surface) == (289000, 4, 3, 77)  # « 289.000 € » = 289 000
    assert (sale.dpe, sale.ges) == ("D", "C")

    rent = conn.parse_detail(fixture("gridimmo_rent.html"), ListingRef(source_id=cfg.id, source_ref="3033", url=url))
    assert (rent.transaction, rent.property_type, rent.city, rent.postal_code) == ("rent", "Garage/parking", "La garenne-colombes", "92250")
    assert (rent.price, rent.surface) == (90, 12)  # « 90 € /mois CC »


def test_louzi_paginated_discovery_and_detail(geo, departments):
    cfg, conn = _source("louzi-immobilier", geo, departments)
    base = cfg.options["list_pages"][0]
    site = FakeSite({base: fixture("louzi_list_page1.html"), base + "?page=2": fixture("louzi_list_page2.html"),
                     base + "?page=3": "<html><body>vide</body></html>"})
    conn = build_connector(cfg, make_ctx(site.client(), geo, departments))
    refs = list(conn.discover())
    assert [r.source_ref for r in refs] == ["2148-700001-1000001", "2148-700002-1000002", "2148-700003-1000003"]  # doublon ignoré
    assert [r.postal_code_hint for r in refs] == ["92000", "95100", "92000"]
    assert any(u.endswith("page=3") for u in site.hits) and not any(u.endswith("page=4") for u in site.hits)  # arrêt à la page vide

    url = refs[0].url
    raw = conn.parse_detail(fixture("louzi_detail.html"), refs[0])
    assert (raw.transaction, raw.property_type, raw.city, raw.postal_code) == ("sale", "Appartement T2", "Ville-Test", "92000")
    assert (raw.price, raw.surface, raw.rooms, raw.bedrooms) == (174000, 32, 2, 1)
    assert raw.description == "Bel appartement F2 très bien agencé." and url.endswith("1000001")
