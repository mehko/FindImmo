/**
 * Export / import des données personnelles (JSON versionné, validé à l'import).
 * Le catalogue n'est pas exporté : il est retéléchargé depuis la source de données.
 */
import { db, type FindImmoDB } from "./db";
import type { AlertRead, Favorite, Ignored, SavedSearch, SettingRow } from "./types";
import { FAVORITE_STATUSES } from "./types";
import { nowIso } from "./utils";

export const BACKUP_VERSION = 1;
const APP = "findimmo";

export interface Backup {
  app: typeof APP;
  kind: "backup";
  version: number;
  exportedAt: string;
  data: {
    searches: SavedSearch[];
    favorites: Favorite[];
    ignored: Ignored[];
    settings: SettingRow[];
    alertsRead: AlertRead[];
  };
}

export class BackupError extends Error {}

export async function exportBackup(database: FindImmoDB = db): Promise<Backup> {
  const [searches, favorites, ignored, settings, alertsRead] = await Promise.all([
    database.searches.toArray(),
    database.favorites.toArray(),
    database.ignored.toArray(),
    database.settings.toArray(),
    database.alertsRead.toArray(),
  ]);
  return { app: APP, kind: "backup", version: BACKUP_VERSION, exportedAt: nowIso(), data: { searches, favorites, ignored, settings, alertsRead } };
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";

function check(cond: boolean, msg: string): asserts cond {
  if (!cond) throw new BackupError(msg);
}

/** Valide la structure et la version. Lève `BackupError` avec un message lisible. */
export function validateBackup(input: unknown): Backup {
  check(isObj(input), "Fichier invalide : objet JSON attendu.");
  check(input.app === APP && input.kind === "backup", "Ce fichier n'est pas une sauvegarde FindImmo.");
  check(typeof input.version === "number", "Version de sauvegarde absente.");
  check(input.version <= BACKUP_VERSION, `Sauvegarde trop récente (v${input.version}) : mettez l'application à jour.`);
  check(isObj(input.data), "Section « data » absente.");
  const d = input.data;
  const list = (k: string) => {
    const v = d[k] ?? [];
    check(Array.isArray(v), `« ${k} » doit être une liste.`);
    return v as unknown[];
  };
  const searches = list("searches");
  searches.forEach((s, i) => {
    check(isObj(s) && isStr(s.id) && isStr(s.name) && isObj(s.criteria), `Recherche n°${i + 1} invalide.`);
    check(Array.isArray((s.criteria as Record<string, unknown>).propertyTypes), `Critères de « ${String(s.name)} » invalides.`);
  });
  const favorites = list("favorites");
  favorites.forEach((f, i) => {
    check(isObj(f) && isStr(f.listingId) && isStr(f.addedAt), `Favori n°${i + 1} invalide.`);
    check(isStr(f.status) && f.status in FAVORITE_STATUSES, `Statut du favori n°${i + 1} inconnu.`);
    check(isObj(f.snapshot), `Favori n°${i + 1} : copie de l'annonce absente.`);
  });
  list("ignored").forEach((x, i) => check(isObj(x) && isStr(x.listingId), `Annonce ignorée n°${i + 1} invalide.`));
  list("settings").forEach((x, i) => check(isObj(x) && isStr(x.key), `Paramètre n°${i + 1} invalide.`));
  list("alertsRead").forEach((x, i) => check(isObj(x) && isStr(x.id), `État d'alerte n°${i + 1} invalide.`));
  return {
    app: APP,
    kind: "backup",
    version: input.version,
    exportedAt: isStr(input.exportedAt) ? input.exportedAt : nowIso(),
    data: {
      searches: searches as SavedSearch[],
      favorites: (favorites as Favorite[]).map((f) => ({ ...f, note: f.note ?? "", updatedAt: f.updatedAt ?? f.addedAt })),
      ignored: list("ignored") as Ignored[],
      settings: list("settings") as SettingRow[],
      alertsRead: list("alertsRead") as AlertRead[],
    },
  };
}

export interface ImportSummary {
  searches: number;
  favorites: number;
  ignored: number;
}

/** `replace` efface les données personnelles existantes ; `merge` ajoute/écrase par identifiant. */
export async function importBackup(input: unknown, mode: "merge" | "replace", database: FindImmoDB = db): Promise<ImportSummary> {
  const b = validateBackup(input);
  await database.transaction("rw", [database.searches, database.favorites, database.ignored, database.settings, database.alertsRead], async () => {
    if (mode === "replace") {
      await Promise.all([database.searches.clear(), database.favorites.clear(), database.ignored.clear(), database.settings.clear(), database.alertsRead.clear()]);
    }
    await database.searches.bulkPut(b.data.searches);
    await database.favorites.bulkPut(b.data.favorites);
    await database.ignored.bulkPut(b.data.ignored);
    await database.settings.bulkPut(b.data.settings);
    await database.alertsRead.bulkPut(b.data.alertsRead);
  });
  return { searches: b.data.searches.length, favorites: b.data.favorites.length, ignored: b.data.ignored.length };
}
