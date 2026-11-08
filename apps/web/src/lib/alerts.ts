/**
 * Alertes calculées localement à partir des événements publiés par le collector :
 * - nouvelles annonces éligibles pour une recherche active ;
 * - baisses/hausses de prix d'annonces éligibles ou en favori ;
 * - changements de disponibilité des favoris.
 */
import type { EventType, Listing, ListingEvent } from "@findimmo/shared";
import { matchListing } from "./match";
import type { SavedSearch } from "./types";

export interface AlertItem {
  id: string;
  type: EventType;
  at: string;
  listingId: string;
  listing?: Listing;
  searches: { id: string; name: string; score: number }[];
  favorite: boolean;
  old?: unknown;
  new?: unknown;
}

const RELEVANT: EventType[] = ["new", "price_drop", "price_increase", "unavailable", "reappeared", "gone"];
/** Une recherche créée aujourd'hui remonte les nouveautés des 3 derniers jours, pas plus. */
const NEW_LOOKBACK_MS = 3 * 86_400_000;

export function computeAlerts(
  events: ListingEvent[],
  listings: Map<string, Listing>,
  searches: SavedSearch[],
  favoriteIds: Set<string>,
  ignoredIds: Set<string>,
  now = Date.now(),
): AlertItem[] {
  const active = searches.filter((s) => s.active);
  const seenNewProperty = new Set<string>();
  const out: AlertItem[] = [];
  for (const e of [...events].sort((a, b) => a.at.localeCompare(b.at))) {
    if (!RELEVANT.includes(e.type) || ignoredIds.has(e.listing_id)) continue;
    const listing = listings.get(e.listing_id);
    if (listing?.property_id && ignoredIds.has(listing.property_id)) continue;
    const favorite = favoriteIds.has(e.listing_id) || (listing?.property_id != null && favoriteIds.has(listing.property_id));
    const matched = listing
      ? active
          .filter((s) => e.type !== "new" || Date.parse(e.at) >= Date.parse(s.createdAt) - NEW_LOOKBACK_MS)
          .map((s) => ({ s, m: matchListing(listing, s.criteria, now) }))
          .filter(({ m }) => m.eligible)
          .map(({ s, m }) => ({ id: s.id, name: s.name, score: m.score }))
      : [];
    let keep = false;
    if (e.type === "new") {
      // Un même bien publié par plusieurs agences ne génère qu'une alerte « nouveau ».
      const key = listing?.property_id ?? e.listing_id;
      keep = matched.length > 0 && !seenNewProperty.has(key);
      if (keep) seenNewProperty.add(key);
    } else if (e.type === "price_drop" || e.type === "price_increase") {
      keep = favorite || matched.length > 0;
    } else {
      keep = favorite;
    }
    if (keep) out.push({ id: e.id, type: e.type, at: e.at, listingId: e.listing_id, listing, searches: matched, favorite, old: e.old, new: e.new });
  }
  return out.reverse();
}
