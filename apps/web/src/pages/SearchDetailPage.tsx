import { useLiveQuery } from "dexie-react-hooks";
import { Pencil, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CriteriaForm } from "@/components/CriteriaForm";
import { EmptyState } from "@/components/EmptyState";
import { ListingCard } from "@/components/ListingCard";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import { toggleFavorite, useFavorites } from "@/hooks/personal";
import { useResults } from "@/hooks/results";
import { db } from "@/lib/db";
import type { SortKey } from "@/lib/match";
import { type Criteria, emptyCriteria } from "@/lib/types";
import { nowIso } from "@/lib/utils";
import { SORTS } from "./ExplorePage";
import { describeCriteria } from "./SearchesPage";

export function SearchDetailPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const search = useLiveQuery(() => db.searches.get(id), [id]);
  const [editing, setEditing] = useState(params.get("edit") === "1");
  const [name, setName] = useState("");
  const [draft, setDraft] = useState<Criteria | null>(null);
  const [sort, setSort] = useState<SortKey>("score");
  const [limit, setLimit] = useState(24);
  const favorites = useFavorites();
  const favIds = useMemo(() => new Set(favorites.map((f) => f.listingId)), [favorites]);

  useEffect(() => {
    if (search && editing && draft === null) {
      setDraft(search.criteria);
      setName(search.name);
    }
  }, [search, editing, draft]);

  const fallback = useMemo(emptyCriteria, []);
  const { items, total } = useResults(search?.criteria ?? fallback, sort);
  if (search === undefined) return <TopBar back title="Recherche" />;
  if (search === null) return null;

  const save = async () => {
    if (!draft) return;
    await db.searches.update(id, { name: name.trim() || "Recherche", criteria: draft, updatedAt: nowIso() });
    setEditing(false);
    setDraft(null);
    setParams({});
  };
  const remove = async () => {
    if (!confirm(`Supprimer la recherche « ${search.name} » ?`)) return;
    await db.searches.delete(id);
    navigate("/recherches");
  };

  return (
    <>
      <TopBar back title={search.name} actions={<>
        <Button variant="ghost" size="icon-sm" onClick={() => { setDraft(search.criteria); setName(search.name); setEditing(true); }} aria-label="Modifier"><Pencil /></Button>
        <Button variant="ghost" size="icon-sm" onClick={() => void remove()} aria-label="Supprimer"><Trash2 /></Button>
      </>} />
      <main className="mx-auto max-w-xl space-y-3 px-4 pb-28">
        <p className="text-sm text-muted-foreground">{describeCriteria(search)}</p>
        <div className="flex items-center justify-between">
          <p className="text-sm"><strong className="tabular-nums">{total}</strong> bien{total > 1 ? "s" : ""}</p>
          <Select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} className="h-9 w-auto text-sm" aria-label="Trier">
            {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </Select>
        </div>
        {items.length === 0 ? (
          <EmptyState icon={Search} title="Aucun bien pour l'instant">Les nouvelles annonces correspondantes apparaîtront dans les alertes.</EmptyState>
        ) : (
          items.slice(0, limit).map((it) => <ListingCard key={it.listing.id} listing={it.listing} match={it.match} sources={it.sources} favorite={favIds.has(it.listing.id)} onFavorite={(l) => void toggleFavorite(l)} />)
        )}
        {items.length > limit && <Button variant="outline" className="w-full" onClick={() => setLimit((l) => l + 24)}>Afficher plus</Button>}
      </main>
      <Sheet open={editing} onOpenChange={(o) => { setEditing(o); if (!o) { setDraft(null); setParams({}); } }} title="Modifier la recherche" footer={<Button className="w-full" onClick={() => void save()}>Enregistrer</Button>}>
        <div className="pt-2">
          <Label htmlFor="search-name">Nom</Label>
          <Input id="search-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        {draft && <CriteriaForm value={draft} onChange={setDraft} />}
      </Sheet>
    </>
  );
}
