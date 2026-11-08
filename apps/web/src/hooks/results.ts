import type { Listing } from "@findimmo/shared";
import { useMemo } from "react";
import { matchListing, type MatchResult, type SortKey, sortResults } from "@/lib/match";
import type { Criteria } from "@/lib/types";
import { useCatalog } from "./catalog";
import { useIgnoredIds } from "./personal";

export interface ResultItem {
  listing: Listing;
  match: MatchResult;
  /** Nombre d'annonces (sources) regroupées pour ce bien. */
  sources: number;
}

/** Annonces éligibles, un seul résultat par bien (l'annonce la moins chère représente le groupe). */
export function useResults(criteria: Criteria, sort: SortKey): { items: ResultItem[]; total: number } {
  const { listings, byProperty } = useCatalog();
  const ignored = useIgnoredIds();
  return useMemo(() => {
    const now = Date.now();
    const best = new Map<string, ResultItem>();
    for (const l of listings) {
      if (l.status === "gone" || ignored.has(l.id) || (l.property_id && ignored.has(l.property_id))) continue;
      const match = matchListing(l, criteria, now);
      if (!match.eligible) continue;
      const key = l.property_id ?? l.id;
      const current = best.get(key);
      if (!current || (l.price ?? Infinity) < (current.listing.price ?? Infinity)) {
        best.set(key, { listing: l, match, sources: byProperty.get(key)?.length ?? 1 });
      }
    }
    const items = sortResults([...best.values()], sort);
    return { items, total: items.length };
  }, [listings, byProperty, ignored, criteria, sort]);
}
