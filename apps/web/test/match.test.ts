import type { Listing } from "@findimmo/shared";
import { describe, expect, it } from "vitest";
import { computeAlerts } from "../src/lib/alerts";
import { matchListing, sortResults } from "../src/lib/match";
import { emptyCriteria, type Criteria, type SavedSearch } from "../src/lib/types";

const NOW = Date.parse("2026-11-08T00:00:00Z");

function listing(over: Partial<Listing> = {}): Listing {
  return {
    id: "fi_1", source_id: "s", source_ref: "1", url: "https://x/1", transaction: "sale", property_type: "house",
    price: 400000, surface: 100, rooms: 5, bedrooms: 3, city: "Meaux", postal_code: "77100", insee_code: "77284",
    department: "77", latitude: 48.96, longitude: 2.88, dpe: "D", features: { garden: true },
    first_seen_at: "2026-11-06T00:00:00Z", last_seen_at: "2026-11-07T00:00:00Z", status: "active",
    price_history: [{ at: "2026-11-06T00:00:00Z", price: 400000 }], ...over,
  };
}

const crit = (over: Partial<Criteria> = {}): Criteria => ({ ...emptyCriteria(), ...over });

describe("éligibilité", () => {
  it("accepte une annonce qui satisfait tous les critères obligatoires", () => {
    const m = matchListing(listing(), crit({ transaction: "sale", propertyTypes: ["house"], departments: ["77"], priceMax: 450000, surfaceMin: 90 }), NOW);
    expect(m.eligible).toBe(true);
    expect(m.failures).toHaveLength(0);
  });

  it("rejette sur un critère obligatoire non satisfait", () => {
    const m = matchListing(listing(), crit({ priceMax: 300000 }), NOW);
    expect(m.eligible).toBe(false);
    expect(m.failures.map((f) => f.key)).toEqual(["price"]);
  });

  it("traite une donnée manquante comme inconnue, selon la politique choisie", () => {
    const l = listing({ dpe: undefined, features: {} });
    const c = crit({ dpeMax: "D", features: { garden: "required" } });
    const keep = matchListing(l, c, NOW);
    expect(keep.eligible).toBe(true);
    expect(keep.unknowns.map((u) => u.key).sort()).toEqual(["dpe", "feature.garden"]);
    expect(matchListing(l, { ...c, missingPolicy: "exclude" }, NOW).eligible).toBe(false);
    // un « false » explicite est un échec, pas une inconnue
    expect(matchListing(listing({ features: { garden: false } }), c, NOW).eligible).toBe(false);
  });

  it("gère zone, rayon, mots-clés, ancienneté et baisse de prix", () => {
    const l = listing({ description: "Maison avec véranda, proche gare" });
    expect(matchListing(l, crit({ postalCodes: ["77100"] }), NOW).eligible).toBe(true);
    expect(matchListing(l, crit({ communes: ["75056"] }), NOW).eligible).toBe(false);
    expect(matchListing(l, crit({ radius: { lat: 48.96, lon: 2.9, km: 5, label: "Meaux" } }), NOW).eligible).toBe(true);
    expect(matchListing(l, crit({ radius: { lat: 43.12, lon: 5.93, km: 20, label: "Toulon" } }), NOW).eligible).toBe(false);
    expect(matchListing(l, crit({ keywordsInclude: ["veranda"] }), NOW).eligible).toBe(true);
    expect(matchListing(l, crit({ keywordsExclude: ["gare"] }), NOW).eligible).toBe(false);
    expect(matchListing(l, crit({ maxAgeDays: 1 }), NOW).eligible).toBe(false);
    expect(matchListing(l, crit({ priceDropOnly: true }), NOW).eligible).toBe(false);
    const dropped = listing({ price: 380000, price_history: [{ at: "a", price: 400000 }, { at: "b", price: 380000 }] });
    expect(matchListing(dropped, crit({ priceDropOnly: true }), NOW).eligible).toBe(true);
  });
});

describe("score", () => {
  it("est déterministe, borné et explicable", () => {
    const c = crit({ priceMax: 450000, surfaceMin: 90, bedroomsMin: 3, dpeMax: "D", features: { garden: "preferred", pool: "preferred" } });
    const a = matchListing(listing(), c, NOW);
    const b = matchListing(listing(), c, NOW);
    expect(a.score).toBe(b.score);
    expect(a.score).toBeGreaterThan(0);
    expect(a.score).toBeLessThanOrEqual(100);
    expect(a.parts.map((p) => p.key)).toEqual(["budget", "surface", "bedrooms", "features", "dpe", "freshness"]);
    const total = a.parts.reduce((s, p) => s + p.max, 0);
    expect(Math.round((a.parts.reduce((s, p) => s + p.points, 0) / total) * 100)).toBe(a.score);
  });

  it("donne la moitié des points à une donnée manquante et la signale", () => {
    const c = crit({ surfaceMin: 90, prefs: { freshness: false } });
    const m = matchListing(listing({ surface: undefined }), c, NOW);
    expect(m.score).toBe(50);
    expect(m.parts[0]!.missing).toBe(true);
  });

  it("classe mieux une annonce moins chère et plus grande", () => {
    const c = crit({ priceMax: 450000, surfaceMin: 90 });
    const cheap = matchListing(listing({ price: 350000, surface: 110 }), c, NOW).score;
    const pricey = matchListing(listing({ price: 445000, surface: 92 }), c, NOW).score;
    expect(cheap).toBeGreaterThan(pricey);
  });

  it("trie par prix en laissant les prix inconnus à la fin", () => {
    const items = [listing({ id: "a", price: 3 }), listing({ id: "b", price: undefined }), listing({ id: "c", price: 1 })].map((l) => ({ listing: l, match: matchListing(l, crit(), NOW) }));
    expect(sortResults(items, "price_asc").map((x) => x.listing.id)).toEqual(["c", "a", "b"]);
  });
});

describe("alertes", () => {
  const search: SavedSearch = { id: "s1", name: "Maison 77", criteria: crit({ departments: ["77"] }), active: true, createdAt: "2026-11-01T00:00:00Z", updatedAt: "2026-11-01T00:00:00Z" };
  const l1 = listing({ id: "fi_1", property_id: "bien_1" });
  const l2 = listing({ id: "fi_2", property_id: "bien_1", source_id: "autre" });
  const l3 = listing({ id: "fi_3", property_id: "bien_3", department: "83" });
  const map = new Map([l1, l2, l3].map((l) => [l.id, l]));
  const ev = (id: string, type: "new" | "price_drop" | "unavailable", lid: string, at = "2026-11-06T00:00:00Z") => ({ id, type, at, listing_id: lid });

  it("signale les nouveautés éligibles une seule fois par bien", () => {
    const out = computeAlerts([ev("e1", "new", "fi_1"), ev("e2", "new", "fi_2"), ev("e3", "new", "fi_3")], map, [search], new Set(), new Set(), NOW);
    expect(out.map((a) => a.id)).toEqual(["e1"]);
    expect(out[0]!.searches[0]!.name).toBe("Maison 77");
  });

  it("suit les favoris et ignore les annonces écartées", () => {
    const events = [ev("e4", "price_drop", "fi_3"), ev("e5", "unavailable", "fi_3"), ev("e6", "price_drop", "fi_1")];
    expect(computeAlerts(events, map, [search], new Set(["fi_3"]), new Set(), NOW).map((a) => a.id)).toEqual(["e6", "e5", "e4"]);
    expect(computeAlerts(events, map, [search], new Set(), new Set(["bien_1"]), NOW)).toHaveLength(0);
  });
});
