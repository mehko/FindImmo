/**
 * Moteur de correspondance déterministe.
 *
 * 1. Éligibilité : chaque critère obligatoire donne `pass`, `fail` ou `unknown` (donnée absente).
 *    Une annonce est éligible si aucun critère n'échoue ; les `unknown` sont gardés « à vérifier »
 *    ou exclus selon `missingPolicy`.
 * 2. Score 0–100 : somme pondérée de composantes actives, normalisée. Une donnée manquante vaut la
 *    moitié des points de la composante (ni bonus ni pénalité arbitraire) et est signalée.
 *
 * `ScoreExtension` permet d'ajouter plus tard une composante (ex. modèle IA local) sans dépendance.
 */
import { DPE_CLASSES, FEATURE_LABELS, type FeatureKey, type Listing, PROPERTY_TYPE_LABELS } from "@findimmo/shared";
import { haversineKm } from "./geo";
import type { Criteria } from "./types";
import { formatPrice } from "./format";

export type CheckState = "pass" | "fail" | "unknown";

export interface Check {
  key: string;
  label: string;
  state: CheckState;
  detail?: string;
}

export interface ScorePart {
  key: string;
  label: string;
  points: number;
  max: number;
  missing: boolean;
  detail: string;
}

export interface MatchResult {
  eligible: boolean;
  checks: Check[];
  unknowns: Check[];
  failures: Check[];
  score: number;
  parts: ScorePart[];
}

export interface ScoreExtension {
  key: string;
  label: string;
  weight: number;
  /** Retourne une valeur dans [0, 1], ou null si non applicable. */
  evaluate(listing: Listing, criteria: Criteria): { value: number | null; detail: string };
}

const DAY = 86_400_000;

function normalizeText(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function listingText(l: Listing): string {
  return normalizeText(`${l.title ?? ""} ${l.description ?? ""} ${l.city ?? ""}`);
}

export function hasPriceDrop(l: Listing): boolean {
  const h = l.price_history;
  if (h.length < 2) return false;
  const first = h[0]!.price;
  const last = h[h.length - 1]!.price;
  return last < first;
}

export function distanceKm(l: Listing, c: Criteria): number | null {
  if (!c.radius || l.latitude == null || l.longitude == null) return null;
  return haversineKm(c.radius.lat, c.radius.lon, l.latitude, l.longitude);
}

function rangeCheck(
  key: string,
  label: string,
  value: number | undefined,
  min: number | undefined,
  max: number | undefined,
  fmt: (n: number) => string,
): Check | null {
  if (min == null && max == null) return null;
  if (value == null) return { key, label, state: "unknown", detail: "non renseigné" };
  const ok = (min == null || value >= min) && (max == null || value <= max);
  return { key, label, state: ok ? "pass" : "fail", detail: fmt(value) };
}

export function evaluateChecks(l: Listing, c: Criteria, now = Date.now()): Check[] {
  const checks: Check[] = [];
  const push = (ch: Check | null) => ch && checks.push(ch);

  if (c.transaction) {
    push(
      l.transaction == null
        ? { key: "transaction", label: "Transaction", state: "unknown" }
        : { key: "transaction", label: "Transaction", state: l.transaction === c.transaction ? "pass" : "fail" },
    );
  }
  if (c.propertyTypes.length) {
    push(
      l.property_type == null
        ? { key: "type", label: "Type de bien", state: "unknown" }
        : {
            key: "type",
            label: "Type de bien",
            state: c.propertyTypes.includes(l.property_type) ? "pass" : "fail",
            detail: PROPERTY_TYPE_LABELS[l.property_type],
          },
    );
  }
  // Localisation : départements, communes, codes postaux sont combinés en OU (zone de recherche).
  const zones = c.departments.length + c.communes.length + c.postalCodes.length;
  if (zones) {
    const known = l.department || l.insee_code || l.postal_code;
    const inZone =
      (l.department != null && c.departments.includes(l.department)) ||
      (l.insee_code != null && c.communes.includes(l.insee_code)) ||
      (l.postal_code != null && c.postalCodes.includes(l.postal_code));
    push({ key: "zone", label: "Localisation", state: inZone ? "pass" : known ? "fail" : "unknown", detail: l.city });
  }
  if (c.radius) {
    const d = distanceKm(l, c);
    const approx = l.provenance?.latitude === "estimated";
    push(
      d == null
        ? { key: "radius", label: `Rayon ${c.radius.km} km`, state: "unknown", detail: "position inconnue" }
        : {
            key: "radius",
            label: `Rayon ${c.radius.km} km`,
            state: d <= c.radius.km ? "pass" : "fail",
            detail: `${approx ? "≈ " : ""}${d.toFixed(1)} km de ${c.radius.label}${approx ? " (centre de la commune)" : ""}`,
          },
    );
  }
  push(rangeCheck("price", "Prix", l.price, c.priceMin, c.priceMax, (n) => formatPrice(n, l.transaction)));
  push(rangeCheck("surface", "Surface", l.surface, c.surfaceMin, c.surfaceMax, (n) => `${n} m²`));
  push(rangeCheck("land", "Terrain", l.land_surface, c.landMin, undefined, (n) => `${n} m²`));
  push(rangeCheck("rooms", "Pièces", l.rooms, c.roomsMin, undefined, String));
  push(rangeCheck("bedrooms", "Chambres", l.bedrooms, c.bedroomsMin, undefined, String));
  if (c.dpeMax) {
    push(
      l.dpe == null
        ? { key: "dpe", label: `DPE ≤ ${c.dpeMax}`, state: "unknown", detail: "DPE non renseigné" }
        : {
            key: "dpe",
            label: `DPE ≤ ${c.dpeMax}`,
            state: DPE_CLASSES.indexOf(l.dpe) <= DPE_CLASSES.indexOf(c.dpeMax) ? "pass" : "fail",
            detail: `DPE ${l.dpe}`,
          },
    );
  }
  for (const [key, wish] of Object.entries(c.features) as [FeatureKey, string][]) {
    if (wish !== "required") continue;
    const v = l.features?.[key];
    push({
      key: `feature.${key}`,
      label: FEATURE_LABELS[key],
      // Absence de mention ≠ absence de l'équipement : état inconnu, sauf « false » explicite.
      state: v === true ? "pass" : v === false ? "fail" : "unknown",
    });
  }
  if (c.keywordsInclude.length || c.keywordsExclude.length) {
    const text = listingText(l);
    for (const kw of c.keywordsInclude) {
      push({ key: `kw+${kw}`, label: `Contient « ${kw} »`, state: text.includes(normalizeText(kw)) ? "pass" : "fail" });
    }
    for (const kw of c.keywordsExclude) {
      push({ key: `kw-${kw}`, label: `Sans « ${kw} »`, state: text.includes(normalizeText(kw)) ? "fail" : "pass" });
    }
  }
  if (c.maxAgeDays != null) {
    const age = (now - Date.parse(l.first_seen_at)) / DAY;
    push({
      key: "age",
      label: `Détectée depuis ≤ ${c.maxAgeDays} j`,
      state: age <= c.maxAgeDays ? "pass" : "fail",
      detail: `${Math.max(0, Math.floor(age))} j`,
    });
  }
  if (c.priceDropOnly) {
    push({ key: "drop", label: "Baisse de prix", state: hasPriceDrop(l) ? "pass" : "fail" });
  }
  return checks;
}

// ---------------------------------------------------------------- score

const WEIGHTS = { location: 20, budget: 20, surface: 20, bedrooms: 10, features: 15, dpe: 10, freshness: 5 };

function part(key: string, label: string, max: number, value: number | null, detail: string): ScorePart {
  const missing = value == null;
  const ratio = missing ? 0.5 : Math.max(0, Math.min(1, value));
  return { key, label, max, points: Math.round(ratio * max * 10) / 10, missing, detail: missing ? `${detail} (inconnu)` : detail };
}

export function scoreParts(l: Listing, c: Criteria, now = Date.now(), extensions: ScoreExtension[] = []): ScorePart[] {
  const parts: ScorePart[] = [];

  if (c.radius) {
    const d = distanceKm(l, c);
    parts.push(part("location", "Proximité", WEIGHTS.location, d == null ? null : 1 - d / Math.max(c.radius.km, 1),
      d == null ? "Distance" : `${d.toFixed(1)} km`));
  }
  // Sans cible explicite : idéal à 85 % du budget maximum, 20 % des points au plafond.
  const target = c.prefs.priceTarget ?? (c.priceMax ? c.priceMax * 0.85 : undefined);
  if (target) {
    let v: number | null = null;
    if (l.price != null) {
      const ceiling = c.priceMax && c.priceMax > target ? c.priceMax : target * 1.15;
      v = l.price <= target ? 1 : l.price > ceiling ? 0 : 1 - (0.8 * (l.price - target)) / (ceiling - target);
    }
    parts.push(part("budget", "Budget", WEIGHTS.budget, v, l.price != null ? formatPrice(l.price, l.transaction) : "Prix"));
  }
  // Sans cible explicite : idéal à 120 % de la surface minimale.
  const sTarget = c.prefs.surfaceTarget ?? (c.surfaceMin ? c.surfaceMin * 1.2 : undefined);
  if (sTarget) {
    const v = l.surface == null ? null : Math.min(1, l.surface / sTarget);
    parts.push(part("surface", "Surface", WEIGHTS.surface, v == null ? null : v * v, l.surface != null ? `${l.surface} m²` : "Surface"));
  }
  const bTarget = c.prefs.bedroomsTarget ?? c.bedroomsMin;
  if (bTarget) {
    const v = l.bedrooms == null ? null : Math.min(1, l.bedrooms / bTarget);
    parts.push(part("bedrooms", "Chambres", WEIGHTS.bedrooms, v, l.bedrooms != null ? `${l.bedrooms} ch.` : "Chambres"));
  }
  const wished = (Object.entries(c.features) as [FeatureKey, string][]).filter(([, w]) => w === "preferred");
  if (wished.length) {
    const known = wished.filter(([k]) => l.features?.[k] != null);
    const got = wished.filter(([k]) => l.features?.[k] === true).map(([k]) => FEATURE_LABELS[k]);
    // Les équipements non mentionnés comptent pour moitié (information inconnue).
    const value = (got.length + (wished.length - known.length) * 0.5) / wished.length;
    parts.push({
      key: "features",
      label: "Équipements",
      max: WEIGHTS.features,
      points: Math.round(value * WEIGHTS.features * 10) / 10,
      missing: known.length < wished.length,
      detail: got.length ? got.join(", ") : "aucun équipement souhaité mentionné",
    });
  }
  const dTarget = c.prefs.dpeTarget ?? c.dpeMax;
  if (dTarget) {
    const v = l.dpe == null ? null : 1 - Math.max(0, DPE_CLASSES.indexOf(l.dpe) - DPE_CLASSES.indexOf(dTarget)) / 3;
    parts.push(part("dpe", "Énergie", WEIGHTS.dpe, v, l.dpe ? `DPE ${l.dpe}` : "DPE"));
  }
  if (c.prefs.freshness) {
    const age = (now - Date.parse(l.first_seen_at)) / DAY;
    parts.push(part("freshness", "Fraîcheur", WEIGHTS.freshness, 1 - Math.min(age, 30) / 30, `détectée il y a ${Math.max(0, Math.floor(age))} j`));
  }
  for (const ext of extensions) {
    const { value, detail } = ext.evaluate(l, c);
    parts.push(part(ext.key, ext.label, ext.weight, value, detail));
  }
  return parts;
}

export function matchListing(l: Listing, c: Criteria, now = Date.now(), extensions: ScoreExtension[] = []): MatchResult {
  const checks = evaluateChecks(l, c, now);
  const failures = checks.filter((x) => x.state === "fail");
  const unknowns = checks.filter((x) => x.state === "unknown");
  const eligible = failures.length === 0 && (c.missingPolicy === "include" || unknowns.length === 0);
  const parts = scoreParts(l, c, now, extensions);
  const max = parts.reduce((s, p) => s + p.max, 0);
  const score = max ? Math.round((parts.reduce((s, p) => s + p.points, 0) / max) * 100) : 50;
  return { eligible, checks, unknowns, failures, score, parts };
}

export type SortKey = "score" | "recent" | "price_asc" | "price_desc" | "ppm2" | "drop";

export function sortResults<T extends { listing: Listing; match: MatchResult }>(items: T[], key: SortKey): T[] {
  const val = (n: number | undefined, fallback: number) => (n == null ? fallback : n);
  const dropPct = (l: Listing) => {
    const h = l.price_history;
    return h.length > 1 ? (h[h.length - 1]!.price - h[0]!.price) / h[0]!.price : 0;
  };
  const cmp: Record<SortKey, (a: T, b: T) => number> = {
    score: (a, b) => b.match.score - a.match.score || b.listing.first_seen_at.localeCompare(a.listing.first_seen_at),
    recent: (a, b) => b.listing.first_seen_at.localeCompare(a.listing.first_seen_at),
    price_asc: (a, b) => val(a.listing.price, Infinity) - val(b.listing.price, Infinity),
    price_desc: (a, b) => val(b.listing.price, -Infinity) - val(a.listing.price, -Infinity),
    ppm2: (a, b) => val(a.listing.price_per_m2, Infinity) - val(b.listing.price_per_m2, Infinity),
    drop: (a, b) => dropPct(a.listing) - dropPct(b.listing),
  };
  return [...items].sort(cmp[key]);
}
