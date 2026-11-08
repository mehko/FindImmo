import { useLiveQuery } from "dexie-react-hooks";
import { useEffect, useMemo } from "react";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { BottomNav } from "@/components/BottomNav";
import { CatalogProvider, useCatalog } from "@/hooks/catalog";
import { useFavorites, useIgnoredIds, useSearches, useSetting } from "@/hooks/personal";
import { computeAlerts } from "@/lib/alerts";
import { db } from "@/lib/db";
import { applyTheme } from "@/lib/theme";
import type { ThemeSetting } from "@/lib/types";
import { AlertsPage } from "@/pages/AlertsPage";
import { ExplorePage } from "@/pages/ExplorePage";
import { FavoritesPage } from "@/pages/FavoritesPage";
import { ListingPage } from "@/pages/ListingPage";
import { SearchDetailPage } from "@/pages/SearchDetailPage";
import { SearchesPage } from "@/pages/SearchesPage";
import { SettingsPage } from "@/pages/SettingsPage";

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function Shell() {
  const { events, byId } = useCatalog();
  const searches = useSearches();
  const favorites = useFavorites();
  const ignored = useIgnoredIds();
  const readIds = useLiveQuery(async () => new Set((await db.alertsRead.toArray()).map((r) => r.id)), [], new Set<string>());
  const [theme] = useSetting<ThemeSetting>("theme", "system");
  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const alerts = useMemo(() => {
    const favIds = new Set<string>();
    for (const f of favorites) {
      favIds.add(f.listingId);
      if (f.propertyId) favIds.add(f.propertyId);
    }
    return computeAlerts(events, byId, searches, favIds, ignored);
  }, [events, byId, searches, favorites, ignored]);
  const unread = alerts.filter((a) => !readIds.has(a.id)).length;

  return (
    <>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<ExplorePage />} />
        <Route path="/recherches" element={<SearchesPage />} />
        <Route path="/recherches/:id" element={<SearchDetailPage />} />
        <Route path="/favoris" element={<FavoritesPage />} />
        <Route path="/alertes" element={<AlertsPage alerts={alerts} />} />
        <Route path="/annonce/:id" element={<ListingPage />} />
        <Route path="/parametres" element={<SettingsPage />} />
        <Route path="*" element={<ExplorePage />} />
      </Routes>
      <BottomNav alertCount={unread} />
    </>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <CatalogProvider>
        <Shell />
      </CatalogProvider>
    </BrowserRouter>
  );
}
