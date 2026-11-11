import { FEATURE_LABELS, type FeatureKey, type Listing, PROPERTY_TYPE_LABELS } from "@findimmo/shared";
import { BedDouble, Building2, Heart, Home, Layers, MapPin, Maximize2, TrendingDown, Trees } from "lucide-react";
import { memo } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { useCatalog } from "@/hooks/catalog";
import { formatPpm2, formatPrice, relativeDays } from "@/lib/format";
import { hasPriceDrop, type MatchResult } from "@/lib/match";
import { cn } from "@/lib/utils";
import { ScoreRing } from "./ScoreRing";

const NEW_MS = 2 * 86_400_000;

export function listingSummary(l: Listing): string {
  const parts: string[] = [];
  if (l.property_type) parts.push(PROPERTY_TYPE_LABELS[l.property_type]);
  if (l.surface) parts.push(`${l.surface} m²`);
  if (l.rooms) parts.push(`${l.rooms} p.`);
  return parts.join(" · ") || l.title || "Annonce";
}

function dropInfo(l: Listing): string | null {
  if (!hasPriceDrop(l)) return null;
  const first = l.price_history[0]!.price;
  const last = l.price_history[l.price_history.length - 1]!.price;
  return `${Math.round(((last - first) / first) * 100)} %`;
}

export const ListingCard = memo(function ListingCard({ listing: l, match, favorite, sources = 1, onFavorite }: { listing: Listing; match?: MatchResult; favorite: boolean; sources?: number; onFavorite: (l: Listing) => void }) {
  const { sources: sourceList } = useCatalog();
  const source = sourceList.find((s) => s.id === l.source_id);
  const sourceName = source?.name ?? l.source_id;
  const isNew = Date.now() - Date.parse(l.first_seen_at) < NEW_MS;
  const drop = dropInfo(l);
  const feats = (Object.entries(l.features ?? {}) as [FeatureKey, boolean][]).filter(([, v]) => v).slice(0, 3);
  const TypeIcon = l.property_type === "apartment" ? Building2 : l.property_type === "land" ? Trees : Home;
  return (
    <article className="animate-fade-up overflow-hidden rounded-2xl border bg-card shadow-[0_1px_2px_rgb(0_0_0/0.04)]">
      <Link to={`/annonce/${l.id}`} className="block">
        <div className="relative aspect-[16/9] bg-muted">
          {l.image ? (
            <img src={l.image} alt="" loading="lazy" decoding="async" referrerPolicy="no-referrer" className="size-full object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
          ) : (
            <div className="grid size-full place-items-center text-muted-foreground/50">
              <TypeIcon className="size-10" />
            </div>
          )}
          <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
            {isNew && <Badge variant="solid">Nouveau</Badge>}
            {drop && (
              <Badge className="bg-success text-white">
                <TrendingDown /> {drop}
              </Badge>
            )}
            {l.status === "unavailable_unconfirmed" && <Badge className="bg-warning text-black">Non retrouvée</Badge>}
            {sources > 1 && (
              <Badge variant="solid">
                <Layers /> {sources} sources
              </Badge>
            )}
          </div>
        </div>
        <div className="flex gap-3 p-4">
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <p className="text-xl font-bold tracking-tight tabular-nums">{formatPrice(l.price, l.transaction)}</p>
              {l.price_per_m2 && l.surface && l.surface >= 9 && <p className="text-xs text-muted-foreground">{formatPpm2(l.price_per_m2, l.transaction)}</p>}
            </div>
            <p className="mt-0.5 truncate text-sm font-medium">{listingSummary(l)}</p>
            <p className="mt-1 flex items-center gap-1 truncate text-sm text-muted-foreground">
              <MapPin className="size-3.5 shrink-0" />
              {l.city ?? "Localisation inconnue"}
              {l.postal_code && ` (${l.postal_code})`}
            </p>
            <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
              {l.bedrooms != null && (
                <Badge variant="muted">
                  <BedDouble /> {l.bedrooms} ch.
                </Badge>
              )}
              {l.land_surface != null && (
                <Badge variant="muted">
                  <Maximize2 /> {l.land_surface} m² terrain
                </Badge>
              )}
              {l.dpe && <Badge variant="muted">DPE {l.dpe}</Badge>}
              {feats.map(([k]) => (
                <Badge key={k} variant="muted">
                  {FEATURE_LABELS[k]}
                </Badge>
              ))}
            </div>
          </div>
          <div className="flex flex-col items-end justify-between">
            {match ? <ScoreRing score={match.score} /> : <span />}
            <span className="text-[11px] text-muted-foreground">{relativeDays(l.first_seen_at)}</span>
          </div>
        </div>
      </Link>
      <div className="flex items-center justify-between border-t px-4 py-2">
        <span className="truncate text-xs text-muted-foreground">
          {l.agency ?? sourceName}
          {source?.attribution && <> · {source.attribution}</>}
          {match && match.unknowns.length > 0 && <span className="ml-1 text-warning">· {match.unknowns.length} critère(s) à vérifier</span>}
        </span>
        <button onClick={() => onFavorite(l)} aria-pressed={favorite} aria-label={favorite ? "Retirer des favoris" : "Ajouter aux favoris"} className="-mr-2 grid size-10 place-items-center rounded-full hover:bg-muted">
          <Heart className={cn("size-5 transition-colors", favorite ? "fill-danger stroke-danger" : "text-muted-foreground")} />
        </button>
      </div>
    </article>
  );
});
