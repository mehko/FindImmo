import { FEATURE_LABELS, type FeatureKey, type Listing, PROPERTY_TYPE_LABELS, PROVENANCE_LABELS } from "@findimmo/shared";
import { useLiveQuery } from "dexie-react-hooks";
import { Check, CircleHelp, ExternalLink, EyeOff, Heart, Info, MapPin, X } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { listingSummary } from "@/components/ListingCard";
import { PriceHistory } from "@/components/PriceHistory";
import { ScoreRing } from "@/components/ScoreRing";
import { TopBar } from "@/components/TopBar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label, Select, Textarea } from "@/components/ui/input";
import { useCatalog } from "@/hooks/catalog";
import { setIgnored, toggleFavorite, updateFavorite, useSearches, useSetting } from "@/hooks/personal";
import { db } from "@/lib/db";
import { formatDate, formatPpm2, formatPrice } from "@/lib/format";
import { matchListing } from "@/lib/match";
import { type Criteria, emptyCriteria, FAVORITE_STATUSES, type FavoriteStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

function Prov({ l, field }: { l: Listing; field: string }) {
  const p = l.provenance?.[field];
  if (!p || p === "extracted") return null;
  return (
    <span title={PROVENANCE_LABELS[p]} className={cn("ml-1 text-[10px] font-semibold uppercase", p === "estimated" ? "text-warning" : "text-muted-foreground")}>
      {p === "estimated" ? "≈ estimé" : p === "parsed" ? "· texte" : "· calculé"}
    </span>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-xl bg-muted/60 px-3 py-2.5">
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-semibold">{children}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card className="p-4">
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {children}
    </Card>
  );
}

export function ListingPage() {
  const { id = "" } = useParams();
  const { byId, byProperty, sources, loading } = useCatalog();
  const l = byId.get(id);
  const favorite = useLiveQuery(() => db.favorites.get(id), [id]);
  const ignored = useLiveQuery(() => db.ignored.get(id), [id]);
  const searches = useSearches();
  const [explore] = useSetting<Criteria>("exploreCriteria", emptyCriteria());
  const [criteriaKey, setCriteriaKey] = useState<string>("auto");
  const [note, setNote] = useState("");
  useEffect(() => {
    setNote(favorite?.note ?? "");
  }, [favorite?.note]);

  const options = useMemo(() => [{ id: "explore", name: "Filtres Explorer", criteria: explore }, ...searches.filter((s) => s.active)], [explore, searches]);
  const chosen = options.find((o) => o.id === criteriaKey) ?? options[1] ?? options[0]!;
  const match = useMemo(() => (l ? matchListing(l, chosen.criteria) : null), [l, chosen]);

  if (!l) {
    return (
      <>
        <TopBar back title="Annonce" />
        <main className="mx-auto max-w-xl px-4 py-10 text-center text-sm text-muted-foreground">
          {loading ? "Chargement…" : favorite ? (
            <>Cette annonce n'est plus dans le catalogue chargé. <a className="text-primary" href={favorite.snapshot.url} target="_blank" rel="noopener noreferrer">Voir l'annonce d'origine</a>.</>
          ) : "Annonce introuvable dans le catalogue chargé."}
        </main>
      </>
    );
  }

  const group = (l.property_id ? byProperty.get(l.property_id) : undefined) ?? [l];
  const sourceName = (sid: string) => sources.find((s) => s.id === sid)?.name ?? sid;
  const features = Object.entries(l.features ?? {}) as [FeatureKey, boolean][];
  const approxGeo = l.provenance?.latitude === "estimated";
  const surfaceReliable = l.surface != null && l.surface >= 9;

  return (
    <>
      <TopBar back title={listingSummary(l)} />
      <main className="mx-auto max-w-xl space-y-3 px-4 pb-28">
        {l.image && (
          <div className="overflow-hidden rounded-2xl bg-muted">
            <img src={l.image} alt="" referrerPolicy="no-referrer" className="aspect-[16/10] w-full object-cover" onError={(e) => (e.currentTarget.parentElement!.style.display = "none")} />
          </div>
        )}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-2xl font-bold tracking-tight tabular-nums">{formatPrice(l.price, l.transaction)}</p>
            {l.price_per_m2 && surfaceReliable ? (
              <p className="text-sm text-muted-foreground">
                {formatPpm2(l.price_per_m2, l.transaction)}
                {l.provenance?.surface === "parsed" && <span className="ml-1 text-xs">(surface lue dans le texte)</span>}
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">Prix au m² non calculable (surface inconnue)</p>
            )}
            <p className="mt-1 flex items-center gap-1 text-sm"><MapPin className="size-4 text-muted-foreground" />{l.city ?? "Commune inconnue"}{l.postal_code && ` (${l.postal_code})`}</p>
          </div>
          {match && <ScoreRing score={match.score} size={56} />}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {l.status === "unavailable_unconfirmed" && <Badge variant="warning">Non retrouvée lors de la dernière collecte (non confirmé)</Badge>}
          {l.price_history.length > 1 && <Badge variant="success">Prix modifié</Badge>}
          {group.length > 1 && <Badge>{group.length} sources pour ce bien</Badge>}
          {l.maybe_same?.length ? <Badge variant="muted">Doublon possible</Badge> : null}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Button asChild><a href={l.url} target="_blank" rel="noopener noreferrer"><ExternalLink /> Annonce d'origine</a></Button>
          <Button variant={favorite ? "secondary" : "outline"} onClick={() => void toggleFavorite(l)}>
            <Heart className={cn(favorite && "fill-danger stroke-danger")} /> {favorite ? "En favori" : "Favori"}
          </Button>
        </div>

        {favorite && (
          <Section title="Mon suivi">
            <Label htmlFor="fav-status">Statut</Label>
            <Select id="fav-status" value={favorite.status} onChange={(e) => void updateFavorite(l.id, { status: e.target.value as FavoriteStatus })}>
              {(Object.keys(FAVORITE_STATUSES) as FavoriteStatus[]).map((s) => <option key={s} value={s}>{FAVORITE_STATUSES[s]}</option>)}
            </Select>
            <Label htmlFor="fav-note" className="mt-3">Notes</Label>
            <Textarea id="fav-note" value={note} placeholder="Questions, impressions de visite…" onChange={(e) => setNote(e.target.value)} onBlur={() => note !== favorite.note && void updateFavorite(l.id, { note })} />
          </Section>
        )}

        <Section title="Caractéristiques">
          <div className="grid grid-cols-2 gap-2">
            <Fact label="Type">{l.property_type ? PROPERTY_TYPE_LABELS[l.property_type] : "—"}<Prov l={l} field="property_type" /></Fact>
            <Fact label="Transaction">{l.transaction === "rent" ? "Location" : l.transaction === "sale" ? "Vente" : "—"}</Fact>
            <Fact label="Surface habitable">{l.surface != null ? `${l.surface} m²` : "—"}<Prov l={l} field="surface" /></Fact>
            <Fact label="Terrain">{l.land_surface != null ? `${l.land_surface} m²` : "—"}<Prov l={l} field="land_surface" /></Fact>
            <Fact label="Pièces">{l.rooms ?? "—"}<Prov l={l} field="rooms" /></Fact>
            <Fact label="Chambres">{l.bedrooms ?? "—"}<Prov l={l} field="bedrooms" /></Fact>
            <Fact label="DPE">{l.dpe ?? "non renseigné"}<Prov l={l} field="dpe" /></Fact>
            <Fact label="GES">{l.ges ?? "non renseigné"}</Fact>
          </div>
          {features.length > 0 ? (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {features.map(([k, v]) => (
                <li key={k}><Badge variant={v ? "default" : "muted"}>{v ? <Check /> : <X />}{FEATURE_LABELS[k]}<Prov l={l} field={`features.${k}`} /></Badge></li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-xs text-muted-foreground">Aucun équipement renseigné par la source.</p>
          )}
          <p className="mt-3 flex items-start gap-1.5 text-[11px] text-muted-foreground"><Info className="mt-px size-3.5 shrink-0" />« texte » : lu dans la description ; « calculé » : déduit exactement ; « estimé » : approximation. Un équipement non mentionné est inconnu, pas absent.</p>
        </Section>

        {match && (
          <Section title={`Correspondance (${match.score}/100)`}>
            <Select value={chosen.id} onChange={(e) => setCriteriaKey(e.target.value)} className="mb-3 h-9 text-sm" aria-label="Critères de comparaison">
              {options.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </Select>
            {match.checks.length === 0 && <p className="text-sm text-muted-foreground">Aucun critère obligatoire défini.</p>}
            <ul className="space-y-1.5">
              {match.checks.map((c) => (
                <li key={c.key} className="flex items-center gap-2 text-sm">
                  {c.state === "pass" ? <Check className="size-4 text-success" /> : c.state === "fail" ? <X className="size-4 text-danger" /> : <CircleHelp className="size-4 text-warning" />}
                  <span className="flex-1">{c.label}</span>
                  <span className="text-xs text-muted-foreground">{c.state === "unknown" ? "à vérifier" : c.detail}</span>
                </li>
              ))}
            </ul>
            {match.parts.length > 0 && (
              <div className="mt-4 space-y-2">
                {match.parts.map((p) => (
                  <div key={p.key}>
                    <div className="flex justify-between text-xs"><span>{p.label} <span className="text-muted-foreground">— {p.detail}</span></span><span className="tabular-nums">{p.points}/{p.max}</span></div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted"><div className={cn("h-full rounded-full", p.missing ? "bg-warning" : "bg-primary")} style={{ width: `${(p.points / p.max) * 100}%` }} /></div>
                  </div>
                ))}
              </div>
            )}
          </Section>
        )}

        <Section title="Historique des prix"><PriceHistory history={l.price_history} transaction={l.transaction} /></Section>

        <Section title="Localisation">
          <p className="text-sm">{l.city ?? "—"} {l.postal_code && `· ${l.postal_code}`} {l.department && `· département ${l.department}`}</p>
          {l.latitude != null && l.longitude != null ? (
            <a className="mt-2 inline-flex items-center gap-1 text-sm text-primary" target="_blank" rel="noopener noreferrer" href={`https://www.openstreetmap.org/?mlat=${l.latitude}&mlon=${l.longitude}#map=${approxGeo ? 13 : 16}/${l.latitude}/${l.longitude}`}>
              <MapPin className="size-4" /> Voir sur la carte {approxGeo && "(centre de la commune : position approximative)"}
            </a>
          ) : (
            <p className="mt-1 text-xs text-muted-foreground">Position non communiquée.</p>
          )}
        </Section>

        {l.description && <Section title="Description (extrait)"><p className="whitespace-pre-line text-sm leading-relaxed text-muted-foreground">{l.description}</p></Section>}

        <Section title="Sources">
          <ul className="divide-y">
            {group.map((g) => (
              <li key={g.id} className="flex items-center justify-between gap-2 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">{g.agency ?? sourceName(g.source_id)}</p>
                  <p className="text-xs text-muted-foreground">détectée le {formatDate(g.first_seen_at)}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold tabular-nums">{formatPrice(g.price, g.transaction)}</p>
                  {g.id === l.id ? <span className="text-xs text-muted-foreground">cette annonce</span> : <Link className="text-xs text-primary" to={`/annonce/${g.id}`}>voir</Link>}
                </div>
              </li>
            ))}
          </ul>
          {l.maybe_same?.length ? (
            <p className="mt-2 text-xs text-muted-foreground">
              Ressemble aussi à : {l.maybe_same.map((m, i) => <span key={m}>{i > 0 && ", "}<Link className="text-primary" to={`/annonce/${m}`}>{byId.get(m)?.city ?? m}</Link></span>)} (rapprochement incertain, non fusionné).
            </p>
          ) : null}
        </Section>

        <Section title="Suivi FindImmo">
          <dl className="grid grid-cols-2 gap-y-1.5 text-sm">
            <dt className="text-muted-foreground">Première détection</dt><dd>{formatDate(l.first_seen_at)}</dd>
            <dt className="text-muted-foreground">Dernière observation</dt><dd>{formatDate(l.last_seen_at)}</dd>
            <dt className="text-muted-foreground">Publiée (source)</dt><dd>{formatDate(l.published_at)}</dd>
            <dt className="text-muted-foreground">Référence</dt><dd className="truncate">{l.source_ref}</dd>
          </dl>
        </Section>

        <Button variant="ghost" className="w-full text-muted-foreground" onClick={() => void setIgnored(l, !ignored)}>
          <EyeOff /> {ignored ? "Ne plus ignorer ce bien" : "Ignorer ce bien"}
        </Button>
      </main>
    </>
  );
}
