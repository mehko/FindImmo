/**
 * Données personnelles, stockées uniquement dans le navigateur (IndexedDB via Dexie).
 * Le catalogue téléchargé est mis en cache dans `catalogFiles` (consultation hors ligne) ;
 * il est remplacé à chaque mise à jour sans jamais toucher aux tables personnelles.
 */
import Dexie, { type EntityTable } from "dexie";
import type { AlertRead, Favorite, Ignored, SavedSearch, SettingRow } from "./types";

export interface CatalogFile {
  path: string;
  kind: "manifest" | "department" | "events" | "communes" | "sources";
  baseUrl: string;
  data: unknown;
  storedAt: string;
}

export class FindImmoDB extends Dexie {
  searches!: EntityTable<SavedSearch, "id">;
  favorites!: EntityTable<Favorite, "listingId">;
  ignored!: EntityTable<Ignored, "listingId">;
  settings!: EntityTable<SettingRow, "key">;
  alertsRead!: EntityTable<AlertRead, "id">;
  catalogFiles!: EntityTable<CatalogFile, "path">;

  constructor(name = "findimmo") {
    super(name);
    this.version(1).stores({
      searches: "id, active, updatedAt",
      favorites: "listingId, propertyId, status, updatedAt",
      ignored: "listingId, propertyId",
      settings: "key",
      alertsRead: "id",
      catalogFiles: "path, kind",
    });
  }
}

export const db = new FindImmoDB();

export async function getSetting<T>(key: string, fallback: T, database: FindImmoDB = db): Promise<T> {
  const row = await database.settings.get(key);
  return row === undefined ? fallback : (row.value as T);
}

export async function setSetting(key: string, value: unknown, database: FindImmoDB = db): Promise<void> {
  await database.settings.put({ key, value });
}
