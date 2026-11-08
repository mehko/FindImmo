import { Bell, ChevronRight, ListFilter, Plus } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useSearches } from "@/hooks/personal";
import { useResults } from "@/hooks/results";
import { db } from "@/lib/db";
import { formatPrice } from "@/lib/format";
import { emptyCriteria, type SavedSearch } from "@/lib/types";
import { nowIso, uid } from "@/lib/utils";
import { PROPERTY_TYPE_LABELS } from "@findimmo/shared";

export function describeCriteria(s: SavedSearch): string {
  const c = s.criteria;
  const parts: string[] = [];
  if (c.transaction) parts.push(c.transaction === "sale" ? "Achat" : "Location");
  if (c.propertyTypes.length) parts.push(c.propertyTypes.map((t) => PROPERTY_TYPE_LABELS[t]).join("/"));
  const zones = [...c.departments, ...c.postalCodes];
  if (zones.length) parts.push(zones.join(", "));
  if (c.communes.length) parts.push(`${c.communes.length} commune(s)`);
  if (c.radius) parts.push(`${c.radius.km} km autour de ${c.radius.label}`);
  if (c.priceMax) parts.push(`≤ ${formatPrice(c.priceMax)}`);
  if (c.surfaceMin) parts.push(`≥ ${c.surfaceMin} m²`);
  if (c.bedroomsMin) parts.push(`${c.bedroomsMin}+ ch.`);
  return parts.join(" · ") || "Tous les biens";
}

function SearchRow({ search }: { search: SavedSearch }) {
  const { total } = useResults(search.criteria, "score");
  return (
    <Card className="flex items-center gap-3 p-4">
      <Link to={`/recherches/${search.id}`} className="min-w-0 flex-1">
        <p className="truncate font-semibold">{search.name}</p>
        <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{describeCriteria(search)}</p>
        <p className="mt-1.5 text-xs font-medium text-primary">{total} bien{total > 1 ? "s" : ""} correspondant{total > 1 ? "s" : ""}</p>
      </Link>
      <div className="flex flex-col items-center gap-1">
        <Switch checked={search.active} onCheckedChange={(v) => void db.searches.update(search.id, { active: v, updatedAt: nowIso() })} label={`Alertes pour ${search.name}`} />
        <span className="text-[10px] text-muted-foreground">{search.active ? "alertes" : "pause"}</span>
      </div>
      <Link to={`/recherches/${search.id}`} aria-label="Modifier" className="text-muted-foreground"><ChevronRight className="size-5" /></Link>
    </Card>
  );
}

export function SearchesPage() {
  const searches = useSearches();
  const navigate = useNavigate();
  const create = async () => {
    const now = nowIso();
    const id = uid();
    await db.searches.put({ id, name: "Nouvelle recherche", criteria: emptyCriteria(), active: true, createdAt: now, updatedAt: now });
    navigate(`/recherches/${id}?edit=1`);
  };
  return (
    <>
      <TopBar title="Mes recherches" actions={<Button size="sm" onClick={() => void create()}><Plus /> Créer</Button>} />
      <main className="mx-auto max-w-xl space-y-3 px-4 pb-28">
        {searches.length === 0 ? (
          <EmptyState icon={ListFilter} title="Aucune recherche enregistrée">
            Créez une recherche pour recevoir des alertes sur les nouvelles annonces et les baisses de prix.
            <Button className="mt-4" onClick={() => void create()}><Plus /> Créer une recherche</Button>
          </EmptyState>
        ) : (
          <>
            <p className="flex items-center gap-2 text-xs text-muted-foreground"><Bell className="size-3.5" /> Les recherches actives alimentent l'onglet Alertes.</p>
            {searches.map((s) => <SearchRow key={s.id} search={s} />)}
          </>
        )}
      </main>
    </>
  );
}
