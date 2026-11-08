import json

from collector.connectors.adapters.laforet import LaforetConnector
from collector.connectors.feed import FeedConnector
from collector.connectors.html import HtmlConnector
from collector.connectors.jsonld import JsonLdConnector, extract_jsonld, raw_from_jsonld
from collector.connectors.registry import build_connector
from collector.connectors.sitemap import iter_sitemap, parse_sitemap
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
