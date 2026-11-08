import { Heart } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { ListingCard } from "@/components/ListingCard";
import { TopBar } from "@/components/TopBar";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { useCatalog } from "@/hooks/catalog";
import { toggleFavorite, useFavorites } from "@/hooks/personal";
import { db } from "@/lib/db";
import { formatPrice } from "@/lib/format";
import { FAVORITE_STATUSES, type FavoriteStatus } from "@/lib/types";

export function FavoritesPage() {
  const favorites = useFavorites();
  const { byId } = useCatalog();
  const [filter, setFilter] = useState<FavoriteStatus | "all">("all");
  const counts = useMemo(() => {
    const c: Partial<Record<FavoriteStatus, number>> = {};
    for (const f of favorites) c[f.status] = (c[f.status] ?? 0) + 1;
    return c;
  }, [favorites]);
  const shown = favorites.filter((f) => filter === "all" || f.status === filter);

  return (
    <>
      <TopBar title="Favoris" />
      <main className="mx-auto max-w-xl space-y-3 px-4 pb-28">
        {favorites.length === 0 ? (
          <EmptyState icon={Heart} title="Aucun favori">Touchez le cœur d'une annonce pour la suivre ici, avec vos notes et votre statut.</EmptyState>
        ) : (
          <>
            <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 [scrollbar-width:none]">
              <Chip active={filter === "all"} onClick={() => setFilter("all")}>Tous · {favorites.length}</Chip>
              {(Object.keys(FAVORITE_STATUSES) as FavoriteStatus[]).filter((s) => counts[s]).map((s) => (
                <Chip key={s} active={filter === s} onClick={() => setFilter(s)}>{FAVORITE_STATUSES[s]} · {counts[s]}</Chip>
              ))}
            </div>
            {shown.map((f) => {
              const live = byId.get(f.listingId);
              return (
                <div key={f.listingId} className="space-y-1.5">
                  {live ? (
                    <ListingCard listing={live} favorite onFavorite={(l) => void toggleFavorite(l)} />
                  ) : (
                    // Annonce absente du catalogue courant : on affiche la copie locale.
                    <Card className="p-4">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="font-semibold">{formatPrice(f.snapshot.price, f.snapshot.transaction)}</p>
                          <p className="truncate text-sm">{f.snapshot.title ?? "Annonce"}</p>
                          <p className="text-sm text-muted-foreground">{f.snapshot.city}</p>
                        </div>
                        <Badge variant="warning">Hors catalogue</Badge>
                      </div>
                      <div className="mt-3 flex gap-3 text-sm">
                        <a href={f.snapshot.url} target="_blank" rel="noopener noreferrer" className="text-primary">Annonce d'origine</a>
                        <button className="text-danger" onClick={() => void db.favorites.delete(f.listingId)}>Retirer</button>
                      </div>
                    </Card>
                  )}
                  <Link to={`/annonce/${f.listingId}`} className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
                    <Badge variant="accent">{FAVORITE_STATUSES[f.status]}</Badge>
                    <span className="truncate">{f.note || "Ajouter une note…"}</span>
                  </Link>
                </div>
              );
            })}
          </>
        )}
      </main>
    </>
  );
}
