import type { Listing } from "@findimmo/shared";
import { useLiveQuery } from "dexie-react-hooks";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { CatalogLoader, type CatalogSnapshot, defaultDataUrl } from "@/lib/catalog";
import { db } from "@/lib/db";

interface CatalogState extends CatalogSnapshot {
  loading: boolean;
  byId: Map<string, Listing>;
  /** Annonces regroupées par bien (dédoublonnage du collector). */
  byProperty: Map<string, Listing[]>;
  dataUrl: string;
  reload: () => void;
}

const empty: CatalogSnapshot = { manifest: null, listings: [], events: [], communes: [], sources: [], offline: false, loadedDepartments: [], error: null };
const Ctx = createContext<CatalogState | null>(null);

export function CatalogProvider({ children }: { children: ReactNode }) {
  // `undefined` tant que IndexedDB n'a pas répondu, `null` si le paramètre n'existe pas.
  const settings = useLiveQuery(async () => {
    const [url, deps] = await Promise.all([db.settings.get("dataUrl"), db.settings.get("departments")]);
    return { url: (url?.value as string | undefined) ?? null, deps: (deps?.value as string[] | undefined) ?? null };
  }, []);
  const ready = settings !== undefined;
  const dataUrl = settings?.url || defaultDataUrl();
  const departments = settings?.deps ?? null;
  const [snap, setSnap] = useState<CatalogSnapshot>(empty);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const run = useRef(0);

  useEffect(() => {
    if (!ready) return;
    const id = ++run.current;
    setLoading(true);
    const loader = new CatalogLoader(dataUrl);
    loader
      .load(departments, (s) => id === run.current && setSnap(s))
      .then((s) => id === run.current && setSnap(s))
      .catch((err: unknown) => id === run.current && setSnap({ ...empty, error: err instanceof Error ? err.message : String(err) }))
      .finally(() => id === run.current && setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataUrl, JSON.stringify(departments), nonce, ready]);

  // Rafraîchit au retour en ligne et lorsque l'application revient au premier plan.
  useEffect(() => {
    const refresh = () => document.visibilityState === "visible" && setNonce((n) => n + 1);
    window.addEventListener("online", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("online", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  const value = useMemo<CatalogState>(() => {
    const byId = new Map(snap.listings.map((l) => [l.id, l]));
    const byProperty = new Map<string, Listing[]>();
    for (const l of snap.listings) {
      const key = l.property_id ?? l.id;
      byProperty.set(key, [...(byProperty.get(key) ?? []), l]);
    }
    return { ...snap, loading, byId, byProperty, dataUrl, reload };
  }, [snap, loading, dataUrl, reload]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useCatalog(): CatalogState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useCatalog hors CatalogProvider");
  return ctx;
}
