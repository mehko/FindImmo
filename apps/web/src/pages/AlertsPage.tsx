import { useLiveQuery } from "dexie-react-hooks";
import { Bell, CheckCheck, EyeOff, Heart, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { listingSummary } from "@/components/ListingCard";
import { TopBar } from "@/components/TopBar";
import { Button } from "@/components/ui/button";
import { db } from "@/lib/db";
import type { AlertItem } from "@/lib/alerts";
import { formatPrice, percent, relativeDays } from "@/lib/format";
import { cn, nowIso } from "@/lib/utils";

const META = {
  new: { icon: Sparkles, label: "Nouvelle annonce", tone: "text-primary bg-primary/12" },
  price_drop: { icon: TrendingDown, label: "Baisse de prix", tone: "text-success bg-success/15" },
  price_increase: { icon: TrendingUp, label: "Hausse de prix", tone: "text-danger bg-danger/12" },
  unavailable: { icon: EyeOff, label: "Annonce non retrouvée (non confirmé)", tone: "text-warning bg-warning/20" },
  reappeared: { icon: Bell, label: "Annonce de retour", tone: "text-primary bg-primary/12" },
  gone: { icon: EyeOff, label: "Annonce retirée", tone: "text-muted-foreground bg-muted" },
  features_changed: { icon: Bell, label: "Caractéristiques modifiées", tone: "text-primary bg-primary/12" },
} as const;

function AlertRow({ a, read }: { a: AlertItem; read: boolean }) {
  const m = META[a.type];
  const Icon = m.icon;
  const l = a.listing;
  const priceChange = (a.type === "price_drop" || a.type === "price_increase") && typeof a.old === "number" && typeof a.new === "number";
  return (
    <Link to={`/annonce/${a.listingId}`} onClick={() => void db.alertsRead.put({ id: a.id, at: nowIso() })} className={cn("flex gap-3 rounded-2xl border bg-card p-3.5 transition-opacity", read && "opacity-60")}>
      <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", m.tone)}><Icon className="size-5" /></span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold">{m.label}</p>
          <span className="shrink-0 text-[11px] text-muted-foreground">{relativeDays(a.at)}</span>
        </div>
        {l ? (
          <p className="truncate text-sm">{listingSummary(l)} · {l.city}</p>
        ) : (
          <p className="text-sm text-muted-foreground">Annonce absente du catalogue chargé</p>
        )}
        <p className="mt-0.5 text-sm font-medium tabular-nums">
          {priceChange ? (
            <>
              <span className="text-muted-foreground line-through">{formatPrice(a.old as number, l?.transaction)}</span> → {formatPrice(a.new as number, l?.transaction)}{" "}
              <span className={a.type === "price_drop" ? "text-success" : "text-danger"}>{percent(a.old as number, a.new as number)}</span>
            </>
          ) : (
            l && formatPrice(l.price, l.transaction)
          )}
        </p>
        <div className="mt-1 flex flex-wrap gap-x-2 text-xs text-muted-foreground">
          {a.favorite && <span className="flex items-center gap-1"><Heart className="size-3 fill-danger stroke-danger" /> favori</span>}
          {a.searches.map((s) => <span key={s.id}>« {s.name} » {s.score}/100</span>)}
        </div>
      </div>
      {!read && <span className="mt-1 size-2 shrink-0 rounded-full bg-primary" aria-label="non lue" />}
    </Link>
  );
}

export function AlertsPage({ alerts }: { alerts: AlertItem[] }) {
  const readIds = useLiveQuery(async () => new Set((await db.alertsRead.toArray()).map((r) => r.id)), [], new Set<string>());
  const unread = alerts.filter((a) => !readIds.has(a.id));
  const markAll = () => void db.alertsRead.bulkPut(unread.map((a) => ({ id: a.id, at: nowIso() })));
  return (
    <>
      <TopBar title="Alertes" actions={unread.length > 0 ? <Button variant="ghost" size="sm" onClick={markAll}><CheckCheck /> Tout lu</Button> : null} />
      <main className="mx-auto max-w-xl space-y-2.5 px-4 pb-28">
        {alerts.length === 0 ? (
          <EmptyState icon={Bell} title="Aucune alerte">Activez une recherche ou ajoutez des favoris : les nouveautés et changements de prix apparaîtront ici à chaque mise à jour du catalogue.</EmptyState>
        ) : (
          alerts.slice(0, 200).map((a) => <AlertRow key={a.id} a={a} read={readIds.has(a.id)} />)
        )}
      </main>
    </>
  );
}
