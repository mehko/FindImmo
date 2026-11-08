from collector.models import EventType, ListingStatus, RawListing, SourceBatch, SourceRunStatus
from collector.pipeline.normalize import listing_id
from collector.pipeline.state import State
from collector.pipeline.tracker import Tracker

from .conftest import make_source

SRC = make_source(id="s1")


def raw(ref: str, price: float, **kw) -> RawListing:
    return RawListing(source_id="s1", source_ref=ref, url=f"https://agence-test.example/{ref}", price=price,
                      surface=kw.pop("surface", 80), city="Meaux", postal_code="77100", transaction="sale",
                      property_type="maison", **kw)


def batch(listings=(), seen=(), ok=True, complete=True) -> SourceBatch:
    return SourceBatch(
        status=SourceRunStatus(source_id="s1", started_at="2026-11-01T00:00:00Z", finished_at="2026-11-01T00:01:00Z",
                               ok=ok, discovery_complete=complete),
        listings=list(listings),
        seen_refs=sorted(set(seen) | {r.source_ref for r in listings}),
    )


def run(state, b, now, geo, departments, settings):
    t = Tracker(state, {"s1": SRC}, geo, departments, settings, now=now)
    t.apply(b)
    return t


def events(state, type_):
    return [e for e in state.events if e.type == type_]


def test_lifecycle(tmp_path, geo, departments, settings):
    st = State(tmp_path)
    t = run(st, batch([raw("A", 300000), raw("B", 200000)]), "2026-11-01T00:00:00Z", geo, departments, settings)
    assert t.stats.new == 2 and len(st.listings) == 2
    a = st.listings[listing_id("s1", "A")]
    assert a.first_seen_at == "2026-11-01T00:00:00Z" and a.department == "77"

    # Baisse de prix sur A ; B vue sans re-téléchargement
    run(st, batch([raw("A", 285000)], seen=["B"]), "2026-11-02T00:00:00Z", geo, departments, settings)
    drop = events(st, EventType.PRICE_DROP)
    assert len(drop) == 1 and (drop[0].old, drop[0].new) == (300000, 285000)
    assert [p.price for p in a.price_history] == [300000, 285000]
    assert a.first_seen_at == "2026-11-01T00:00:00Z"  # inchangé

    # Source en échec : rien ne doit changer
    run(st, batch(ok=False, complete=False), "2026-11-03T00:00:00Z", geo, departments, settings)
    assert all(x.status == ListingStatus.ACTIVE for x in st.listings.values())
    # Découverte partielle : rien ne doit changer non plus
    run(st, batch(seen=["A"], complete=False), "2026-11-03T01:00:00Z", geo, departments, settings)
    assert st.listings[listing_id("s1", "B")].status == ListingStatus.ACTIVE

    # B absente d'une découverte complète → non confirmée (pas « vendue »)
    run(st, batch(seen=["A"]), "2026-11-04T00:00:00Z", geo, departments, settings)
    b = st.listings[listing_id("s1", "B")]
    assert b.status == ListingStatus.UNAVAILABLE_UNCONFIRMED and len(events(st, EventType.UNAVAILABLE)) == 1

    # B réapparaît
    run(st, batch(seen=["A", "B"]), "2026-11-05T00:00:00Z", geo, departments, settings)
    assert b.status == ListingStatus.ACTIVE and len(events(st, EventType.REAPPEARED)) == 1

    # B absente longtemps et plusieurs fois → retirée probable
    for day in ("06", "08", "11", "14"):
        run(st, batch(seen=["A"]), f"2026-11-{day}T00:00:00Z", geo, departments, settings)
    assert b.status == ListingStatus.GONE and len(events(st, EventType.GONE)) == 1


def test_price_increase_and_feature_change(tmp_path, geo, departments, settings):
    st = State(tmp_path)
    run(st, batch([raw("A", 300000, features={"garden": True})]), "2026-11-01T00:00:00Z", geo, departments, settings)
    run(st, batch([raw("A", 310000, surface=85)]), "2026-11-02T00:00:00Z", geo, departments, settings)
    assert len(events(st, EventType.PRICE_INCREASE)) == 1
    ch = events(st, EventType.FEATURES_CHANGED)
    assert len(ch) == 1 and ch[0].old == {"surface": 80} and ch[0].new == {"surface": 85}
    # une information connue n'est pas effacée par une collecte qui ne la mentionne plus
    assert st.listings[listing_id("s1", "A")].features == {"garden": True}


def test_out_of_scope_listing_is_not_kept(tmp_path, geo, departments, settings):
    st = State(tmp_path)
    r = RawListing(source_id="s1", source_ref="L", url="https://x/l", price=1, city="Lyon", postal_code="69003")
    t = run(st, batch([r]), "2026-11-01T00:00:00Z", geo, departments, settings)
    assert not st.listings and t.stats.out_of_scope == 1
    assert "L" in st.source_refs("s1").out_of_scope


def test_state_roundtrip(tmp_path, geo, departments, settings):
    st = State(tmp_path)
    run(st, batch([raw("A", 300000)]), "2026-11-01T00:00:00Z", geo, departments, settings)
    st.save()
    again = State.load(tmp_path)
    assert again.listings.keys() == st.listings.keys() and len(again.events) == 1
