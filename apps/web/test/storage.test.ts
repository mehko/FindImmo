import "fake-indexeddb/auto";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { BackupError, exportBackup, importBackup, validateBackup } from "../src/lib/backup";
import { CatalogLoader } from "../src/lib/catalog";
import { FindImmoDB } from "../src/lib/db";
import { emptyCriteria } from "../src/lib/types";

const DEMO = join(__dirname, "..", "public", "demo-data");
let n = 0;
const freshDb = () => new FindImmoDB(`test-${++n}`);

function demoFetcher(opts: { offline?: boolean; calls?: string[] } = {}) {
  return async (url: string) => {
    opts.calls?.push(url);
    if (opts.offline) throw new TypeError("Failed to fetch");
    const path = new URL(url).pathname.replace(/^\/demo-data\//, "");
    try {
      return new Response(readFileSync(join(DEMO, path), "utf-8"), { status: 200 });
    } catch {
      return new Response("not found", { status: 404 });
    }
  };
}

async function seed(db: FindImmoDB) {
  await db.searches.put({ id: "s1", name: "Var", criteria: { ...emptyCriteria(), departments: ["83"] }, active: true, createdAt: "2026-11-01T00:00:00Z", updatedAt: "2026-11-01T00:00:00Z" });
  await db.favorites.put({ listingId: "fi_x", addedAt: "2026-11-02T00:00:00Z", updatedAt: "2026-11-02T00:00:00Z", status: "visit_planned", note: "Visite samedi", snapshot: { url: "https://x", title: "Maison" } });
  await db.settings.put({ key: "theme", value: "dark" });
}

describe("catalogue", () => {
  it("charge progressivement le jeu de démonstration et le met en cache", async () => {
    const db = freshDb();
    const progress: number[] = [];
    const loader = new CatalogLoader("http://localhost/demo-data/", demoFetcher(), db);
    const snap = await loader.load(null, (s) => progress.push(s.loadedDepartments.length));
    expect(snap.error).toBeNull();
    expect(snap.manifest?.demo).toBe(true);
    expect(snap.listings.length).toBe(snap.manifest?.total_listings);
    expect(progress).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect(snap.events.length).toBeGreaterThan(0);
    expect(snap.communes.length).toBeGreaterThan(1000);
  });

  it("fonctionne hors ligne à partir du cache, et ne retélécharge pas les fichiers hashés", async () => {
    const db = freshDb();
    await new CatalogLoader("http://localhost/demo-data/", demoFetcher(), db).load(["83"]);
    const calls: string[] = [];
    const again = await new CatalogLoader("http://localhost/demo-data/", demoFetcher({ calls }), db).load(["83"]);
    expect(calls.map((c) => new URL(c).pathname)).toEqual(["/demo-data/manifest.json"]);
    const offline = await new CatalogLoader("http://localhost/demo-data/", demoFetcher({ offline: true }), db).load(["83"]);
    expect(offline.offline).toBe(true);
    expect(offline.listings.length).toBe(again.listings.length);
  });

  it("une mise à jour du catalogue ne touche pas aux données personnelles", async () => {
    const db = freshDb();
    await seed(db);
    await new CatalogLoader("http://localhost/demo-data/", demoFetcher(), db).load(null);
    expect(await db.favorites.count()).toBe(1);
    expect((await db.favorites.get("fi_x"))?.note).toBe("Visite samedi");
    expect(await db.searches.count()).toBe(1);
  });
});

describe("sauvegarde", () => {
  it("exporte puis réimporte (remplacement)", async () => {
    const a = freshDb();
    await seed(a);
    const backup = JSON.parse(JSON.stringify(await exportBackup(a)));
    const b = freshDb();
    await b.favorites.put({ listingId: "autre", addedAt: "x", updatedAt: "x", status: "new", note: "", snapshot: { url: "u" } });
    const summary = await importBackup(backup, "replace", b);
    expect(summary).toEqual({ searches: 1, favorites: 1, ignored: 0 });
    expect(await b.favorites.get("autre")).toBeUndefined();
    expect((await b.settings.get("theme"))?.value).toBe("dark");
  });

  it("fusionne sans effacer", async () => {
    const a = freshDb();
    await seed(a);
    const b = freshDb();
    await b.favorites.put({ listingId: "autre", addedAt: "x", updatedAt: "x", status: "new", note: "", snapshot: { url: "u" } });
    await importBackup(await exportBackup(a), "merge", b);
    expect(await b.favorites.count()).toBe(2);
  });

  it("refuse les fichiers invalides avec un message clair", () => {
    expect(() => validateBackup("x")).toThrow(BackupError);
    expect(() => validateBackup({ app: "autre", kind: "backup", version: 1, data: {} })).toThrow(/pas une sauvegarde/);
    expect(() => validateBackup({ app: "findimmo", kind: "backup", version: 99, data: {} })).toThrow(/trop récente/);
    expect(() => validateBackup({ app: "findimmo", kind: "backup", version: 1, data: { favorites: [{ listingId: "a", addedAt: "x", status: "zzz", snapshot: {} }] } })).toThrow(/Statut/);
    expect(validateBackup({ app: "findimmo", kind: "backup", version: 1, data: {} }).data.searches).toEqual([]);
  });
});
