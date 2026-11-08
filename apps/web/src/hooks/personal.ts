import type { Listing } from "@findimmo/shared";
import { useLiveQuery } from "dexie-react-hooks";
import { db, setSetting } from "@/lib/db";
import type { Favorite, FavoriteStatus, SavedSearch } from "@/lib/types";
import { nowIso } from "@/lib/utils";

export function useFavorites(): Favorite[] {
  return useLiveQuery(() => db.favorites.orderBy("updatedAt").reverse().toArray(), [], []);
}

export function useSearches(): SavedSearch[] {
  return useLiveQuery(() => db.searches.orderBy("updatedAt").reverse().toArray(), [], []);
}

export function useIgnoredIds(): Set<string> {
  const rows = useLiveQuery(() => db.ignored.toArray(), [], []);
  const ids = new Set<string>();
  for (const r of rows) {
    ids.add(r.listingId);
    if (r.propertyId) ids.add(r.propertyId);
  }
  return ids;
}

export function useSetting<T>(key: string, fallback: T): [T, (v: T) => Promise<void>] {
  const row = useLiveQuery(() => db.settings.get(key), [key]);
  const value = row === undefined ? fallback : (row.value as T);
  return [value, (v: T) => setSetting(key, v)];
}

export function snapshotOf(l: Listing): Favorite["snapshot"] {
  const { title, price, city, postal_code, url, image, surface, property_type, transaction } = l;
  return { title, price, city, postal_code, url, image, surface, property_type, transaction };
}

export async function toggleFavorite(l: Listing): Promise<boolean> {
  const existing = await db.favorites.get(l.id);
  if (existing) {
    await db.favorites.delete(l.id);
    return false;
  }
  const now = nowIso();
  await db.favorites.put({ listingId: l.id, propertyId: l.property_id, addedAt: now, updatedAt: now, status: "new", note: "", snapshot: snapshotOf(l) });
  return true;
}

export async function updateFavorite(id: string, patch: Partial<Pick<Favorite, "status" | "note">> & { status?: FavoriteStatus }): Promise<void> {
  await db.favorites.update(id, { ...patch, updatedAt: nowIso() });
}

export async function setIgnored(l: Listing, ignored: boolean): Promise<void> {
  if (ignored) await db.ignored.put({ listingId: l.id, propertyId: l.property_id, at: nowIso() });
  else await db.ignored.delete(l.id);
}
