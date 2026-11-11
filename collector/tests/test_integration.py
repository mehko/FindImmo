"""Pipeline complet sur un site d'agence simulé : deux collectes successives."""

import json

from collector.collect import run_collect, shard_of
from collector.config import load_departments
from collector.models import EventType
from collector.pipeline.state import State
from collector.process import report_markdown, run_process
from collector.schema import DepartmentFile, EventsFile, Manifest

from .conftest import FakeSite, make_source

BASE = "https://agence-test.example"
PATTERN = r"/annonces/vente/[^/]+/[^/]+-(?P<postal_code>\d{5})/(?P<ref>[A-Z0-9]+)$"


def page(ref: str, price: int, city: str, cp: str, surface: float = 80) -> str:
    data = {
        "@context": "https://schema.org", "@type": "RealEstateListing", "name": f"Maison {surface} m²",
        "mainEntity": {"@type": "Offer", "price": price, "businessFunction": "http://purl.org/goodrelations/v1#Sell",
                       "itemOffered": {"@type": "House", "floorSize": {"value": surface}, "numberOfRooms": 4,
                                       "address": {"addressLocality": city, "postalCode": cp}}},
    }
    return f'<html><head><script type="application/ld+json">{json.dumps(data)}</script></head></html>'


def sitemap(refs: list[tuple[str, str, str]]) -> str:
    urls = "".join(f"<url><loc>{BASE}/annonces/vente/maison/{slug}-{cp}/{ref}</loc></url>" for ref, slug, cp in refs)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'


def test_two_runs_end_to_end(tmp_path, geo, departments, settings):
    refs = [("M1", "meaux", "77100"), ("M2", "toulon", "83000"), ("M3", "lyon", "69003")]
    site = FakeSite({
        f"{BASE}/robots.txt": "User-agent: *\nDisallow: /admin/\n",
        f"{BASE}/sitemap.xml": sitemap(refs),
        f"{BASE}/annonces/vente/maison/meaux-77100/M1": page("M1", 250000, "Meaux", "77100"),
        f"{BASE}/annonces/vente/maison/toulon-83000/M2": page("M2", 320000, "Toulon", "83000"),
        f"{BASE}/annonces/vente/maison/lyon-69003/M3": page("M3", 1, "Lyon", "69003"),
    })
    src = make_source(options={"sitemaps": [f"{BASE}/sitemap.xml"], "url_pattern": PATTERN}, max_details_per_run=10)
    other = make_source(id="cassee", domain="cassee.example", url="https://cassee.example",
                        options={"sitemaps": ["https://cassee.example/sitemap.xml"], "url_pattern": PATTERN})
    deps = load_departments()
    state_dir, raw_dir, public = tmp_path / "state", tmp_path / "raw", tmp_path / "public"

    def cycle(now: str):
        client = site.client()
        run_collect([src, other], geo, departments, State.load(state_dir), settings, raw_dir, client=client)
        return run_process(raw_dir, state_dir, public, [src, other], deps, geo, settings, now=now)

    r1 = cycle("2026-11-01T00:00:00Z")
    assert r1["new_listings"] == 2 and r1["sources_error"] == 1  # la source cassée n'empêche rien
    assert site.hits.get(f"{BASE}/annonces/vente/maison/lyon-69003/M3") is None  # hors zone : jamais téléchargée

    manifest = Manifest.model_validate_json((public / "manifest.json").read_text())
    assert manifest.total_listings == 2 and not manifest.demo
    dep77 = next(d for d in manifest.departments if d.code == "77")
    assert dep77.count == 1 and dep77.path.startswith("listings/77.")
    listing = DepartmentFile.model_validate_json((public / dep77.path).read_text()).listings[0]
    assert listing.city == "Meaux" and listing.price == 250000 and listing.first_seen_at == "2026-11-01T00:00:00Z"

    # 2e passage : baisse de prix sur M1 (lastmod inchangé mais rafraîchissement forcé : refresh_days=0)
    site.set(f"{BASE}/annonces/vente/maison/meaux-77100/M1", page("M1", 239000, "Meaux", "77100"))
    src.refresh_days = 0
    r2 = cycle("2026-11-02T00:00:00Z")
    assert r2["new_listings"] == 0 and r2["price_drops"] == 1

    # 3e passage : M2 disparaît du sitemap → non confirmée, toujours publiée avec ce statut
    site.set(f"{BASE}/sitemap.xml", sitemap(refs[:1]))
    src.refresh_days = 30
    hits_before = site.hits[f"{BASE}/annonces/vente/maison/meaux-77100/M1"]
    r3 = cycle("2026-11-03T00:00:00Z")
    assert r3["unavailable"] == 1
    assert site.hits[f"{BASE}/annonces/vente/maison/meaux-77100/M1"] == hits_before  # pas re-téléchargée
    manifest = Manifest.model_validate_json((public / "manifest.json").read_text())
    dep83 = next(d for d in manifest.departments if d.code == "83")
    l83 = DepartmentFile.model_validate_json((public / dep83.path).read_text()).listings[0]
    assert l83.status == "unavailable_unconfirmed"

    ev = EventsFile.model_validate_json((public / manifest.files.events.path).read_text())
    types = [e.type for e in ev.events]
    assert types.count(EventType.NEW) == 2 and EventType.PRICE_DROP in types and EventType.UNAVAILABLE in types
    assert not (tmp_path / "public.tmp").exists()  # publication atomique terminée
    assert "Rapport de collecte" in report_markdown(r3)


def test_budget_limits_detail_fetches(tmp_path, geo, departments, settings):
    refs = [(f"R{i}", "meaux", "77100") for i in range(5)]
    site = FakeSite({f"{BASE}/sitemap.xml": sitemap(refs)})
    for ref, slug, cp in refs:
        site.set(f"{BASE}/annonces/vente/maison/{slug}-{cp}/{ref}", page(ref, 100000 + int(ref[1:]), "Meaux", cp))
    src = make_source(options={"sitemaps": [f"{BASE}/sitemap.xml"], "url_pattern": PATTERN}, max_details_per_run=2)
    [b] = run_collect([src], geo, departments, State(tmp_path), settings, tmp_path / "raw", client=site.client())
    assert b.status.details_fetched == 2 and b.status.backlog == 3 and b.status.discovery_complete


def test_shards_partition_sources():
    ids = [f"s{i}" for i in range(20)]
    parts = [{s for s in ids if shard_of(s, 3) == k} for k in range(3)]
    assert set().union(*parts) == set(ids) and sum(len(p) for p in parts) == 20


def test_stops_after_consecutive_unparseable_pages(tmp_path, geo, departments, settings):
    refs = [(f"R{i}", "meaux", "77100") for i in range(15)]
    site = FakeSite({f"{BASE}/sitemap.xml": sitemap(refs)})
    for ref, slug, cp in refs:
        site.set(f"{BASE}/annonces/vente/maison/{slug}-{cp}/{ref}", "<html><title>Accès restreint</title></html>")
    src = make_source(options={"sitemaps": [f"{BASE}/sitemap.xml"], "url_pattern": PATTERN}, max_details_per_run=50)
    [b] = run_collect([src], geo, departments, State(tmp_path), settings, tmp_path / "raw", client=site.client())
    assert b.status.details_failed == 10
    assert b.status.errors[0].startswith("arrêt")
    assert "Accès restreint" in b.status.errors[1]


def test_removed_listings_redirect_and_intermittent_soft_404(tmp_path, geo, departments, settings):
    """Redirection (Laforêt) = annonce retirée. Page de liste en 200 (Citya) = échec temporaire, retenté."""
    refs = [("OK1", "meaux", "77100"), ("RED", "meaux", "77100"), ("SOFT", "meaux", "77100")]
    catalog = ('<html><title>Achat/vente immobilière Meaux</title><script type="application/ld+json">'
               '{"@type":"OfferCatalog","itemListElement":[]}</script></html>')
    soft = f"{BASE}/annonces/vente/maison/meaux-77100/SOFT"
    site = FakeSite({
        f"{BASE}/sitemap.xml": sitemap(refs),
        f"{BASE}/annonces/vente/maison/meaux-77100/OK1": page("OK1", 200000, "Meaux", "77100"),
        f"{BASE}/annonces/vente/maison/meaux-77100/RED": (301, f"{BASE}/ville/meaux"),
        f"{BASE}/ville/meaux": "<html><title>Maisons à vendre à Meaux</title></html>",
        soft: catalog,
    })
    src = make_source(options={"sitemaps": [f"{BASE}/sitemap.xml"], "url_pattern": PATTERN})
    deps = load_departments()
    state_dir = tmp_path / "state"

    def cycle(now):
        [b] = run_collect([src], geo, departments, State.load(state_dir), settings, tmp_path / "raw", client=site.client())
        run_process(tmp_path / "raw", state_dir, tmp_path / "public", [src], deps, geo, settings, now=now)
        return b

    b = cycle("2026-11-01T00:00:00Z")
    assert (b.status.details_fetched, b.status.removed, b.status.details_failed) == (1, 1, 1)
    assert site.hits[soft] == 2  # un nouvel essai dans la même collecte
    assert "page de liste reçue" in b.status.errors[0]

    # Collecte suivante : la page redirigée n'est plus demandée, la page de liste est retentée et réussit
    site.set(soft, page("SOFT", 180000, "Meaux", "77100"))
    red_hits = site.hits[f"{BASE}/annonces/vente/maison/meaux-77100/RED"]
    b2 = cycle("2026-11-02T00:00:00Z")
    assert b2.status.removed == 0 and not b2.status.errors
    assert "SOFT" in {x.source_ref for x in State.load(state_dir).listings.values()}
    assert site.hits[f"{BASE}/annonces/vente/maison/meaux-77100/RED"] == red_hits

    # Une annonce connue qui devient redirigée passe en « non retrouvée » (pas « vendue »)
    site.set(f"{BASE}/annonces/vente/maison/meaux-77100/OK1", (301, f"{BASE}/ville/meaux"))
    src.refresh_days = 0
    cycle("2026-11-03T00:00:00Z")
    st = State.load(state_dir)
    assert sorted(x.status.value for x in st.listings.values()) == ["active", "unavailable_unconfirmed"]


def test_partial_discovery_never_infers_removal_from_absence(tmp_path, geo, departments, settings):
    """Option ``partial_discovery`` : une annonce absente de la découverte est revérifiée par sa propre page."""
    m1, m2 = f"{BASE}/annonces/vente/maison/meaux-77100/M1", f"{BASE}/annonces/vente/maison/toulon-83000/M2"
    refs = [("M1", "meaux", "77100"), ("M2", "toulon", "83000")]
    site = FakeSite({
        f"{BASE}/robots.txt": "User-agent: *\nDisallow: /admin/\n",
        f"{BASE}/sitemap.xml": sitemap(refs),
        m1: page("M1", 250000, "Meaux", "77100"),
        m2: page("M2", 320000, "Toulon", "83000"),
    })
    src = make_source(options={"sitemaps": [f"{BASE}/sitemap.xml"], "url_pattern": PATTERN, "partial_discovery": True},
                      max_details_per_run=10, refresh_days=0)
    deps = load_departments()
    state_dir, raw_dir, public = tmp_path / "state", tmp_path / "raw", tmp_path / "public"

    def cycle(now: str):
        run_collect([src], geo, departments, State.load(state_dir), settings, raw_dir, client=site.client())
        return run_process(raw_dir, state_dir, public, [src], deps, geo, settings, now=now)

    def status_of(code: str) -> str:
        manifest = Manifest.model_validate_json((public / "manifest.json").read_text())
        path = next(d for d in manifest.departments if d.code == code).path
        return DepartmentFile.model_validate_json((public / path).read_text()).listings[0].status

    assert cycle("2026-11-01T00:00:00Z")["new_listings"] == 2

    # M2 sort de la découverte (liste plafonnée) mais sa page répond toujours : elle reste active, sans alerte.
    site.set(f"{BASE}/sitemap.xml", sitemap(refs[:1]))
    hits_before = site.hits[m2]
    r2 = cycle("2026-11-02T00:00:00Z")
    assert site.hits[m2] == hits_before + 1  # revérifiée directement
    assert r2["unavailable"] == 0 and status_of("83") == "active"

    # Sa page disparaît : retrait CONFIRMÉ → indisponible ; M1, toujours découverte, reste active.
    site.set(m2, (404, "introuvable"))
    r3 = cycle("2026-11-03T00:00:00Z")
    assert r3["unavailable"] == 1 and status_of("83") == "unavailable_unconfirmed" and status_of("77") == "active"

    # Absence durable confirmée : la page n'est plus retéléchargée, le cycle de vie suit son cours jusqu'à « gone ».
    hits_after_removal = site.hits[m2]
    cycle("2026-11-05T00:00:00Z")
    r5 = cycle("2026-11-12T00:00:00Z")
    assert site.hits[m2] == hits_after_removal and r5["gone"] == 1


def test_complete_discovery_is_unchanged_without_the_option(tmp_path, geo, departments, settings):
    """Sans l'option, l'absence du sitemap reste un signal (comportement historique)."""
    m2 = f"{BASE}/annonces/vente/maison/toulon-83000/M2"
    refs = [("M1", "meaux", "77100"), ("M2", "toulon", "83000")]
    site = FakeSite({f"{BASE}/robots.txt": "", f"{BASE}/sitemap.xml": sitemap(refs),
                     f"{BASE}/annonces/vente/maison/meaux-77100/M1": page("M1", 250000, "Meaux", "77100"), m2: page("M2", 320000, "Toulon", "83000")})
    src = make_source(options={"sitemaps": [f"{BASE}/sitemap.xml"], "url_pattern": PATTERN}, max_details_per_run=10, refresh_days=30)
    state_dir, raw_dir, public = tmp_path / "state", tmp_path / "raw", tmp_path / "public"

    def cycle(now: str):
        run_collect([src], geo, departments, State.load(state_dir), settings, raw_dir, client=site.client())
        return run_process(raw_dir, state_dir, public, [src], load_departments(), geo, settings, now=now)

    cycle("2026-11-01T00:00:00Z")
    site.set(f"{BASE}/sitemap.xml", sitemap(refs[:1]))
    hits = site.hits[m2]
    assert cycle("2026-11-02T00:00:00Z")["unavailable"] == 1 and site.hits[m2] == hits  # pas de revérification


def test_hide_unavailable_and_attribution_are_published(tmp_path, geo, departments, settings):
    """Source sous accord : mention de source publiée ; une annonce retirée de la source disparaît de l'affichage."""
    m1, m2 = f"{BASE}/annonces/vente/maison/meaux-77100/M1", f"{BASE}/annonces/vente/maison/toulon-83000/M2"
    refs = [("M1", "meaux", "77100"), ("M2", "toulon", "83000")]
    site = FakeSite({f"{BASE}/robots.txt": "", f"{BASE}/sitemap.xml": sitemap(refs),
                     m1: page("M1", 250000, "Meaux", "77100"), m2: page("M2", 320000, "Toulon", "83000")})
    src = make_source(options={"sitemaps": [f"{BASE}/sitemap.xml"], "url_pattern": PATTERN}, max_details_per_run=10,
                      refresh_days=30, attribution="Source : Test Immo", hide_unavailable=True)
    plain = make_source(id="libre", domain="libre.example", url="https://libre.example",
                        options={"sitemaps": ["https://libre.example/sitemap.xml"], "url_pattern": PATTERN})
    state_dir, raw_dir, public = tmp_path / "state", tmp_path / "raw", tmp_path / "public"

    def cycle(now: str):
        run_collect([src], geo, departments, State.load(state_dir), settings, raw_dir, client=site.client())
        return run_process(raw_dir, state_dir, public, [src, plain], load_departments(), geo, settings, now=now)

    def published(code: str):
        manifest = Manifest.model_validate_json((public / "manifest.json").read_text())
        path = next(d for d in manifest.departments if d.code == code).path
        return DepartmentFile.model_validate_json((public / path).read_text()).listings

    cycle("2026-11-01T00:00:00Z")
    sources = json.loads((public / json.loads((public / "manifest.json").read_text())["files"]["sources"]["path"]).read_text())["sources"]
    by_id = {s["id"]: s for s in sources}
    assert by_id[src.id]["attribution"] == "Source : Test Immo" and by_id["libre"]["attribution"] is None
    assert [x.status for x in published("83")] == ["active"]

    site.set(f"{BASE}/sitemap.xml", sitemap(refs[:1]))  # M2 sort du sitemap → indisponible
    assert cycle("2026-11-02T00:00:00Z")["unavailable"] == 1
    assert published("83") == [] and len(published("77")) == 1  # M2 masquée, M1 toujours affichée

    src.hide_unavailable = False  # sans l'option, l'annonce non confirmée reste affichée avec son statut
    cycle("2026-11-03T00:00:00Z")
    assert [x.status for x in published("83")] == ["unavailable_unconfirmed"]
