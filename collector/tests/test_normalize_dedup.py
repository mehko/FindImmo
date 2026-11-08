from collector.models import Listing, Provenance, RawListing
from collector.pipeline.dedup import deduplicate, score_pair
from collector.pipeline.normalize import listing_id, normalize, normalize_url

from .conftest import make_source


def raw(**kw) -> RawListing:
    base = {"source_id": "test", "source_ref": "R1", "url": "https://agence-test.example/r1"}
    base.update(kw)
    return RawListing(**base)


def test_listing_id_is_stable_and_source_scoped():
    assert listing_id("a", "1") == listing_id("a", "1")
    assert listing_id("a", "1") != listing_id("b", "1")
    assert listing_id("a", "1").startswith("fi_")


def test_normalize_url():
    assert normalize_url("https://WWW.Site.fr/annonce/12/?utm_source=x#top") == "https://site.fr/annonce/12"


def test_normalize_geo_and_provenance(geo):
    v = normalize(raw(city="CHATOU", postal_code="78400", price=500000, surface=100, transaction="vente",
                      property_type="Maison"), make_source(), geo)
    assert v["department"] == "78" and v["insee_code"] == "78146" and v["city"] == "Chatou"
    assert v["transaction"] == "sale" and v["property_type"] == "house"
    assert v["price_per_m2"] == 5000
    # Pas de GPS dans la source → centre de la commune, explicitement marqué « estimé »
    assert v["latitude"] is not None and v["provenance"]["latitude"] == Provenance.ESTIMATED
    assert v["provenance"]["price_per_m2"] == Provenance.COMPUTED


def test_normalize_insee_code_in_place_of_postal_code(geo):
    v = normalize(raw(city="Toulon", postal_code="83137"), make_source(), geo)
    assert v["insee_code"] == "83137" and v["department"] == "83"
    assert v["postal_code"] is None  # Toulon a plusieurs codes postaux : on ne devine pas


def test_normalize_features_false_ignored_unless_trusted(geo):
    r = raw(features={"cellar": False, "parking": True}, description="Avec jardin et sans piscine")
    v = normalize(r, make_source(), geo)
    assert v["features"] == {"parking": True, "garden": True}
    assert v["provenance"]["features.garden"] == Provenance.PARSED
    v = normalize(r, make_source(trust_false_features=True), geo)
    assert v["features"]["cellar"] is False


def test_normalize_never_invents_missing_values(geo):
    v = normalize(raw(), make_source(), geo)
    for field in ("price", "surface", "rooms", "bedrooms", "dpe", "department", "price_per_m2", "latitude"):
        assert v[field] is None
    assert v["features"] == {}


def test_normalize_rejects_invalid_values(geo):
    v = normalize(raw(price=0, surface=-3, dpe="Z", latitude=0.0, longitude=0.0), make_source(), geo)
    assert v["price"] is None and v["surface"] is None and v["dpe"] is None and v["latitude"] is None


def L(id_, source="a", **kw) -> Listing:
    base = {"id": id_, "source_id": source, "source_ref": id_, "url": f"https://{source}.example/{id_}",
            "first_seen_at": "2026-11-01T00:00:00Z", "last_seen_at": "2026-11-01T00:00:00Z",
            "transaction": "sale", "property_type": "house", "insee_code": "77186", "postal_code": "77300"}
    base.update(kw)
    return Listing(**base)


def test_dedup_merges_strong_cross_source_match():
    a = L("fi_a", "a", surface=120, price=480000, rooms=5, bedrooms=4, dpe="C")
    b = L("fi_b", "b", surface=120.5, price=485000, rooms=5, bedrooms=4, dpe="C", first_seen_at="2026-11-02T00:00:00Z")
    groups, cands = deduplicate([a, b])
    assert len(groups) == 1 and not cands
    assert a.property_id == b.property_id == "bien_a"  # l'annonce la plus ancienne donne l'ID


def test_dedup_flags_uncertain_match_without_merging():
    # Surface et prix proches mais aucune autre caractéristique : incertain
    a = L("fi_a", "a", surface=120, price=480000)
    b = L("fi_b", "b", surface=121.5, price=470000)
    groups, cands = deduplicate([a, b])
    assert not groups and len(cands) == 1
    assert a.property_id != b.property_id


def test_dedup_never_merges_same_source_or_distinct_properties():
    a = L("fi_a", "a", surface=60, price=300000, rooms=3)
    b = L("fi_b", "a", surface=60, price=300000, rooms=3)
    c = L("fi_c", "c", surface=60, price=300000, rooms=3, dpe="G")
    d = L("fi_d", "d", surface=60, price=300000, rooms=3, transaction="rent")
    assert score_pair(a, b) is None and score_pair(a, d) is None
    groups, _ = deduplicate([a, b, d])
    assert not groups
    res = score_pair(L("fi_a2", "a", surface=60, price=300000, rooms=3, dpe="C"), c)
    assert res is not None and res[0] < 0.8  # DPE différent : pénalité


def test_dedup_requires_surface_on_both_sides():
    assert score_pair(L("fi_a", "a", price=1), L("fi_b", "b", price=1)) is None


def test_dedup_same_url_level1():
    a = L("fi_a", "a", url="https://www.portail.example/annonce/9/")
    b = L("fi_b", "b", url="https://portail.example/annonce/9")
    groups, _ = deduplicate([a, b])
    assert len(groups) == 1 and groups[0].level == 1
