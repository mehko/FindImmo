/**
 * Chargement du catalogue publié (GitHub Pages ou jeu de démonstration local).
 *
 * - `manifest.json` est toujours redemandé au réseau ; en cas d'échec, la dernière version en
 *   cache IndexedDB est utilisée (mode hors ligne).
 * - Les fichiers de données ont un nom hashé : s'ils sont déjà en cache, aucun téléchargement.
 * - Chargement progressif : chaque département est publié dès qu'il est disponible.
 * - Si un fichier hashé a disparu (publication intervenue entre-temps), le manifest est relu une fois.
 */
import { FORMAT_VERSION, isManifest, type Commune, type DepartmentFile, type EventsFile, type Listing, type ListingEvent, type Manifest, type SourceInfo } from "@findimmo/shared";
import { type CatalogFile, db, type FindImmoDB } from "./db";
import { nowIso } from "./utils";

export interface CatalogSnapshot {
  manifest: Manifest | null;
  listings: Listing[];
  events: ListingEvent[];
  communes: Commune[];
  sources: SourceInfo[];
  offline: boolean;
  loadedDepartments: string[];
  error: string | null;
}

export type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;

export class HttpError extends Error {
  constructor(public status: number, url: string) {
    super(`HTTP ${status} : ${url}`);
  }
}

export function defaultDataUrl(): string {
  const env = import.meta.env?.VITE_DATA_URL as string | undefined;
  return env && env.length > 0 ? env : `${import.meta.env?.BASE_URL ?? "/"}demo-data/`;
}

export function normalizeBase(url: string): string {
  return url.endsWith("/") ? url : `${url}/`;
}

export class CatalogLoader {
  constructor(
    private baseUrl: string,
    private fetcher: Fetcher = (u, i) => fetch(u, i),
    private database: FindImmoDB = db,
  ) {
    this.baseUrl = normalizeBase(baseUrl);
  }

  private async getJson<T>(path: string, init?: RequestInit): Promise<T> {
    const url = new URL(path, new URL(this.baseUrl, globalThis.location?.href ?? "http://localhost/")).toString();
    const resp = await this.fetcher(url, init);
    if (!resp.ok) throw new HttpError(resp.status, url);
    return (await resp.json()) as T;
  }

  async loadManifest(): Promise<{ manifest: Manifest; offline: boolean }> {
    try {
      const manifest = await this.getJson<unknown>("manifest.json", { cache: "no-cache" });
      if (!isManifest(manifest)) throw new Error("manifest invalide");
      if (manifest.format_version > FORMAT_VERSION) {
        throw new Error(`Format de données v${manifest.format_version} non pris en charge : mettez l'application à jour.`);
      }
      await this.database.catalogFiles.put({ path: "manifest.json", kind: "manifest", baseUrl: this.baseUrl, data: manifest, storedAt: nowIso() });
      return { manifest, offline: false };
    } catch (err) {
      const cached = await this.database.catalogFiles.get("manifest.json");
      if (cached && cached.baseUrl === this.baseUrl && isManifest(cached.data)) return { manifest: cached.data, offline: true };
      throw err;
    }
  }

  /** Fichier hashé : lu depuis le cache s'il existe, sinon téléchargé puis mis en cache. */
  async loadFile<T>(path: string, kind: CatalogFile["kind"]): Promise<T> {
    const cached = await this.database.catalogFiles.get(path);
    if (cached && cached.baseUrl === this.baseUrl) return cached.data as T;
    const data = await this.getJson<T>(path);
    await this.database.catalogFiles.put({ path, kind, baseUrl: this.baseUrl, data, storedAt: nowIso() });
    return data;
  }

  /** Supprime du cache les fichiers qui ne font plus partie du manifest courant. */
  async pruneCache(manifest: Manifest): Promise<void> {
    const keep = new Set<string>(["manifest.json", ...manifest.departments.map((d) => d.path), ...Object.values(manifest.files).filter(Boolean).map((f) => f!.path)]);
    const all = await this.database.catalogFiles.toArray();
    const stale = all.filter((f) => !keep.has(f.path) || f.baseUrl !== this.baseUrl).map((f) => f.path);
    if (stale.length) await this.database.catalogFiles.bulkDelete(stale);
  }

  async load(departments: string[] | null, onProgress?: (s: CatalogSnapshot) => void, retry = true): Promise<CatalogSnapshot> {
    const { manifest, offline } = await this.loadManifest();
    const snap: CatalogSnapshot = { manifest, listings: [], events: [], communes: [], sources: [], offline, loadedDepartments: [], error: null };
    const wanted = manifest.departments.filter((d) => !departments || departments.length === 0 || departments.includes(d.code));
    try {
      // Départements les plus petits d'abord : premier affichage plus rapide.
      for (const dep of [...wanted].sort((a, b) => a.bytes - b.bytes)) {
        const file = await this.loadFile<DepartmentFile>(dep.path, "department");
        snap.listings = snap.listings.concat(file.listings);
        snap.loadedDepartments = [...snap.loadedDepartments, dep.code];
        onProgress?.({ ...snap });
      }
      snap.events = (await this.loadFile<EventsFile>(manifest.files.events.path, "events")).events;
      snap.sources = (await this.loadFile<{ sources: SourceInfo[] }>(manifest.files.sources.path, "sources")).sources;
      if (manifest.files.communes) {
        snap.communes = (await this.loadFile<{ communes: Commune[] }>(manifest.files.communes.path, "communes")).communes;
      }
    } catch (err) {
      if (retry && err instanceof HttpError && err.status === 404 && !offline) {
        return this.load(departments, onProgress, false);
      }
      snap.error = err instanceof Error ? err.message : String(err);
      return snap;
    }
    if (!offline) await this.pruneCache(manifest);
    return snap;
  }
}
