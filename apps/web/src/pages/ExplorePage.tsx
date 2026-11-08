import { ArrowDownUp, Bookmark, Search, SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { CriteriaForm } from "@/components/CriteriaForm";
import { EmptyState } from "@/components/EmptyState";
import { ListingCard } from "@/components/ListingCard";
import { StatusBanner } from "@/components/StatusBanner";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input, Select } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import { useCatalog } from "@/hooks/catalog";
import { toggleFavorite, useFavorites, useSearches, useSetting } from "@/hooks/personal";
import { useResults } from "@/hooks/results";
import { db } from "@/lib/db";
import type { SortKey } from "@/lib/match";
import { type Criteria, emptyCriteria } from "@/lib/types";
import { nowIso, uid } from "@/lib/utils";

const PAGE = 24;
export const SORTS: { value: SortKey; label: string }[] = [
  { value: "score", label: "Pertinence" },
  { value: "recent", label: "Plus récentes" },
  { value: "price_asc", label: "Prix croissant" },
  { value: "price_desc", label: "Prix décroissant" },
  { value: "ppm2", label: "Prix au m²" },
  { value: "drop", label: "Plus fortes baisses" },
];

function activeCount(c: Criteria): number {
  return [c.transaction, c.propertyTypes.length, c.departments.length + c.communes.length + c.postalCodes.length, c.radius, c.priceMin ?? c.priceMax, c.surfaceMin ?? c.surfaceMax, c.landMin, c.roomsMin, c.bedroomsMin, c.dpeMax, Object.keys(c.features).length, c.keywordsInclude.length + c.keywordsExclude.length, c.maxAgeDays, c.priceDropOnly || undefined].filter((x) => x !== undefined && x !== 0).length;
}

export function ExplorePage() {
  const navigate = useNavigate();
  const { listings, loading } = useCatalog();
  const [stored, setStored] = useSetting<Criteria>("exploreCriteria", emptyCriteria());
  const [sort, setSort] = useSetting<SortKey>("exploreSort", "score");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Criteria>(stored);
  const [limit, setLimit] = useState(PAGE);
  const favorites = useFavorites();
  const searches = useSearches();
  const favIds = useMemo(() => new Set(favorites.map((f) => f.listingId)), [favorites]);

  const criteria = useMemo<Criteria>(() => {
    const words = query.trim();
    return words ? { ...stored, keywordsInclude: [...stored.keywordsInclude, ...words.split(/\s+/)] } : stored;
  }, [stored, query]);
  const { items, total } = useResults(criteria, sort);
  const n = activeCount(stored);

  const quick = (patch: Partial<Criteria>) => void setStored({ ...stored, ...patch });
  const saveAsSearch = async (c: Criteria) => {
    const now = nowIso();
    const id = uid();
    await db.searches.put({ id, name: `Recherche du ${new Date().toLocaleDateString("fr-FR")}`, criteria: c, active: true, createdAt: now, updatedAt: now });
    navigate(`/recherches/${id}`);
  };

  return (
    <>
      <TopBar />
      <main className="mx-auto max-w-xl space-y-3 px-4 pb-28">
        <StatusBanner />
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-muted-foreground" />
          <Input value={query} onChange={(e) => { setQuery(e.target.value); setLimit(PAGE); }} placeholder="Ville, mot-clé (ex. jardin)…" className="pl-9" type="search" />
        </div>
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
          <Chip active={n > 0} onClick={() => { setDraft(stored); setOpen(true); }}>
            <SlidersHorizontal /> Filtres{n > 0 && ` · ${n}`}
          </Chip>
          <Chip active={stored.transaction === "sale"} onClick={() => quick({ transaction: stored.transaction === "sale" ? undefined : "sale" })}>Achat</Chip>
          <Chip active={stored.transaction === "rent"} onClick={() => quick({ transaction: stored.transaction === "rent" ? undefined : "rent" })}>Location</Chip>
          <Chip active={stored.propertyTypes.includes("house")} onClick={() => quick({ propertyTypes: stored.propertyTypes.includes("house") ? stored.propertyTypes.filter((t) => t !== "house") : [...stored.propertyTypes, "house"] })}>Maison</Chip>
          <Chip active={stored.propertyTypes.includes("apartment")} onClick={() => quick({ propertyTypes: stored.propertyTypes.includes("apartment") ? stored.propertyTypes.filter((t) => t !== "apartment") : [...stored.propertyTypes, "apartment"] })}>Appartement</Chip>
          <Chip active={stored.priceDropOnly} onClick={() => quick({ priceDropOnly: !stored.priceDropOnly })}>Baisse de prix</Chip>
          <Chip active={stored.maxAgeDays === 3} onClick={() => quick({ maxAgeDays: stored.maxAgeDays === 3 ? undefined : 3 })}>Moins de 3 j</Chip>
        </div>
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-muted-foreground">
            <strong className="text-foreground tabular-nums">{total}</strong> bien{total > 1 ? "s" : ""}
            {listings.length > 0 && <span> sur {listings.length} annonces</span>}
          </p>
          <label className="relative flex items-center gap-1 text-sm">
            <ArrowDownUp className="pointer-events-none absolute left-2.5 size-3.5 text-muted-foreground" />
            <Select value={sort} onChange={(e) => void setSort(e.target.value as SortKey)} className="h-9 w-auto pl-7 text-sm" aria-label="Trier">
              {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </Select>
          </label>
        </div>
        {searches.length > 0 && (
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none]">
            {searches.slice(0, 6).map((s) => (
              <Chip key={s.id} onClick={() => { void setStored(s.criteria); setLimit(PAGE); }}>
                <Bookmark /> {s.name}
              </Chip>
            ))}
          </div>
        )}
        {items.length === 0 && !loading ? (
          <EmptyState icon={Search} title="Aucun bien ne correspond">Élargissez vos filtres ou vérifiez la source de données dans les paramètres.</EmptyState>
        ) : (
          <div className="space-y-3">
            {items.slice(0, limit).map((it) => (
              <ListingCard key={it.listing.id} listing={it.listing} match={it.match} sources={it.sources} favorite={favIds.has(it.listing.id)} onFavorite={(l) => void toggleFavorite(l)} />
            ))}
            {items.length > limit && (
              <Button variant="outline" className="w-full" onClick={() => setLimit((l) => l + PAGE)}>
                Afficher plus ({items.length - limit} restants)
              </Button>
            )}
          </div>
        )}
      </main>
      <Sheet
        open={open}
        onOpenChange={setOpen}
        title="Filtres"
        footer={
          <div className="grid grid-cols-[auto_1fr] gap-2">
            <Button variant="ghost" onClick={() => setDraft(emptyCriteria())}>Réinitialiser</Button>
            <Button onClick={() => { void setStored(draft); setOpen(false); setLimit(PAGE); }}>Appliquer</Button>
          </div>
        }
      >
        <CriteriaForm value={draft} onChange={setDraft} />
        <Button variant="outline" className="mb-2 w-full" onClick={() => { void setStored(draft).then(() => saveAsSearch(draft)); setOpen(false); }}>
          <Bookmark /> Enregistrer comme recherche
        </Button>
      </Sheet>
    </>
  );
}
