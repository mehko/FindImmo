import { type Commune, DPE_CLASSES, type DpeClass, FEATURE_KEYS, FEATURE_LABELS, type FeatureKey, PROPERTY_TYPE_LABELS, type PropertyType } from "@findimmo/shared";
import { Crosshair, Search, X } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { Chip, Segmented } from "@/components/ui/chip";
import { Input, Label, NumberInput, Select } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useCatalog } from "@/hooks/catalog";
import { foldText } from "@/lib/geo";
import type { Criteria, FeatureWish } from "@/lib/types";
import { cn } from "@/lib/utils";

const TYPES: PropertyType[] = ["apartment", "house", "land", "parking", "commercial", "building"];

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="border-b py-5 last:border-0">
      <h3 className="text-sm font-semibold">{title}</h3>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      <div className="mt-3 space-y-3">{children}</div>
    </section>
  );
}

function Pair({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-3">{children}</div>;
}

function parseList(s: string): string[] {
  return s.split(",").map((x) => x.trim()).filter(Boolean);
}

function CommunePicker({ communes, onPick, placeholder }: { communes: Commune[]; onPick: (c: Commune) => void; placeholder: string }) {
  const [q, setQ] = useState("");
  const results = useMemo(() => {
    const f = foldText(q);
    if (f.length < 2) return [];
    return communes.filter((c) => foldText(c.name).includes(f) || c.cps.some((cp) => cp.startsWith(q.trim()))).slice(0, 6);
  }, [q, communes]);
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-muted-foreground" />
      <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} className="pl-9" />
      {results.length > 0 && (
        <ul className="absolute inset-x-0 top-12 z-10 overflow-hidden rounded-xl border bg-card shadow-lg">
          {results.map((c) => (
            <li key={c.insee}>
              <button type="button" className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm hover:bg-muted" onClick={() => { onPick(c); setQ(""); }}>
                <span>{c.name}</span>
                <span className="text-xs text-muted-foreground">{c.cps.slice(0, 2).join(", ")} · {c.dep}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CriteriaForm({ value, onChange }: { value: Criteria; onChange: (c: Criteria) => void }) {
  const { manifest, communes } = useCatalog();
  const set = <K extends keyof Criteria>(k: K, v: Criteria[K]) => onChange({ ...value, [k]: v });
  const setPref = <K extends keyof Criteria["prefs"]>(k: K, v: Criteria["prefs"][K]) => onChange({ ...value, prefs: { ...value.prefs, [k]: v } });
  const byInsee = useMemo(() => new Map(communes.map((c) => [c.insee, c])), [communes]);
  const [geoError, setGeoError] = useState<string | null>(null);

  const toggle = <T,>(list: T[], item: T) => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);
  const cycleFeature = (k: FeatureKey) => {
    const order: (FeatureWish | undefined)[] = [undefined, "preferred", "required"];
    const next = order[(order.indexOf(value.features[k]) + 1) % order.length];
    const features = { ...value.features };
    if (next) features[k] = next;
    else delete features[k];
    set("features", features);
  };
  const locate = () => {
    setGeoError(null);
    navigator.geolocation?.getCurrentPosition(
      (pos) => set("radius", { lat: pos.coords.latitude, lon: pos.coords.longitude, km: value.radius?.km ?? 10, label: "ma position" }),
      () => setGeoError("Position indisponible (autorisation refusée ou hors ligne)."),
      { timeout: 10000 },
    );
  };

  return (
    <div>
      <Section title="Projet">
        <Segmented
          value={value.transaction ?? "any"}
          onChange={(v) => set("transaction", v === "any" ? undefined : v)}
          options={[{ value: "any", label: "Tout" }, { value: "sale", label: "Achat" }, { value: "rent", label: "Location" }]}
        />
        <div className="flex flex-wrap gap-2">
          {TYPES.map((t) => (
            <Chip key={t} active={value.propertyTypes.includes(t)} onClick={() => set("propertyTypes", toggle(value.propertyTypes, t))}>
              {PROPERTY_TYPE_LABELS[t]}
            </Chip>
          ))}
        </div>
      </Section>

      <Section title="Localisation" hint="Départements, communes et codes postaux se cumulent (zone de recherche).">
        <div className="flex flex-wrap gap-2">
          {(manifest?.departments ?? []).map((d) => (
            <Chip key={d.code} active={value.departments.includes(d.code)} onClick={() => set("departments", toggle(value.departments, d.code))}>
              {d.code} <span className="font-normal opacity-75">{d.name}</span>
            </Chip>
          ))}
        </div>
        <CommunePicker communes={communes} placeholder="Ajouter une commune ou un code postal" onPick={(c) => !value.communes.includes(c.insee) && set("communes", [...value.communes, c.insee])} />
        {(value.communes.length > 0 || value.postalCodes.length > 0) && (
          <div className="flex flex-wrap gap-2">
            {value.communes.map((insee) => (
              <Chip key={insee} active onClick={() => set("communes", value.communes.filter((x) => x !== insee))}>
                {byInsee.get(insee)?.name ?? insee} <X />
              </Chip>
            ))}
            {value.postalCodes.map((cp) => (
              <Chip key={cp} active onClick={() => set("postalCodes", value.postalCodes.filter((x) => x !== cp))}>
                {cp} <X />
              </Chip>
            ))}
          </div>
        )}
        <div>
          <Label>Codes postaux (séparés par des virgules)</Label>
          <Input defaultValue={value.postalCodes.join(", ")} key={value.postalCodes.join()} inputMode="numeric" placeholder="ex. 77300, 83400" onBlur={(e) => set("postalCodes", parseList(e.target.value).filter((x) => /^\d{5}$/.test(x)))} />
        </div>
        <div className="rounded-xl bg-muted/60 p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">Rayon autour d'un point</span>
            {value.radius && (
              <button type="button" className="text-xs text-primary" onClick={() => set("radius", undefined)}>
                Retirer
              </button>
            )}
          </div>
          {value.radius ? (
            <div className="mt-2 space-y-2">
              <p className="text-sm text-muted-foreground">Centre : {value.radius.label}</p>
              <div className="flex items-center gap-3">
                <input type="range" min={1} max={60} value={value.radius.km} onChange={(e) => set("radius", { ...value.radius!, km: Number(e.target.value) })} className="flex-1 accent-[var(--primary)]" aria-label="Rayon en km" />
                <span className="w-14 text-right text-sm font-semibold tabular-nums">{value.radius.km} km</span>
              </div>
            </div>
          ) : (
            <div className="mt-2 space-y-2">
              <CommunePicker communes={communes} placeholder="Commune centre du rayon" onPick={(c) => c.lat != null && c.lon != null && set("radius", { lat: c.lat, lon: c.lon, km: 10, label: c.name })} />
              <button type="button" onClick={locate} className="flex items-center gap-2 text-sm font-medium text-primary">
                <Crosshair className="size-4" /> Utiliser ma position
              </button>
              {geoError && <p className="text-xs text-danger">{geoError}</p>}
            </div>
          )}
        </div>
      </Section>

      <Section title="Budget et surfaces" hint="Min/max sont obligatoires ; les valeurs « idéales » n'influencent que le score.">
        <Pair>
          <div><Label>Prix min (€)</Label><NumberInput value={value.priceMin} onValue={(v) => set("priceMin", v)} /></div>
          <div><Label>Prix max (€)</Label><NumberInput value={value.priceMax} onValue={(v) => set("priceMax", v)} /></div>
        </Pair>
        <Pair>
          <div><Label>Surface min (m²)</Label><NumberInput value={value.surfaceMin} onValue={(v) => set("surfaceMin", v)} /></div>
          <div><Label>Surface max (m²)</Label><NumberInput value={value.surfaceMax} onValue={(v) => set("surfaceMax", v)} /></div>
        </Pair>
        <Pair>
          <div><Label>Terrain min (m²)</Label><NumberInput value={value.landMin} onValue={(v) => set("landMin", v)} /></div>
          <div><Label>Pièces min</Label><NumberInput value={value.roomsMin} onValue={(v) => set("roomsMin", v)} /></div>
        </Pair>
        <Pair>
          <div><Label>Chambres min</Label><NumberInput value={value.bedroomsMin} onValue={(v) => set("bedroomsMin", v)} /></div>
          <div>
            <Label>DPE au plus</Label>
            <Select value={value.dpeMax ?? ""} onChange={(e) => set("dpeMax", (e.target.value || undefined) as DpeClass | undefined)}>
              <option value="">Indifférent</option>
              {DPE_CLASSES.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          </div>
        </Pair>
      </Section>

      <Section title="Équipements" hint="Touchez pour alterner : indifférent → souhaité (score) → obligatoire.">
        <div className="flex flex-wrap gap-2">
          {FEATURE_KEYS.map((k) => {
            const w = value.features[k];
            return (
              <Chip key={k} active={w === "required"} onClick={() => cycleFeature(k)} className={cn(w === "preferred" && "border-primary bg-primary/10 text-primary")}>
                {FEATURE_LABELS[k]}
                {w && <span className="text-[10px] font-semibold uppercase opacity-80">{w === "required" ? "oblig." : "souhaité"}</span>}
              </Chip>
            );
          })}
        </div>
      </Section>

      <Section title="Mots-clés et ancienneté">
        <div><Label>Doit contenir (virgules)</Label><Input defaultValue={value.keywordsInclude.join(", ")} key={`i${value.keywordsInclude.join()}`} placeholder="ex. véranda, cheminée" onBlur={(e) => set("keywordsInclude", parseList(e.target.value))} /></div>
        <div><Label>Exclure (virgules)</Label><Input defaultValue={value.keywordsExclude.join(", ")} key={`e${value.keywordsExclude.join()}`} placeholder="ex. viager, travaux" onBlur={(e) => set("keywordsExclude", parseList(e.target.value))} /></div>
        <div>
          <Label>Détectée depuis</Label>
          <Select value={value.maxAgeDays ?? ""} onChange={(e) => set("maxAgeDays", e.target.value ? Number(e.target.value) : undefined)}>
            <option value="">Peu importe</option>
            {[1, 3, 7, 14, 30].map((d) => <option key={d} value={d}>moins de {d} jour{d > 1 ? "s" : ""}</option>)}
          </Select>
        </div>
        <label className="flex items-center justify-between gap-3 text-sm">
          <span>Uniquement les baisses de prix</span>
          <Switch checked={value.priceDropOnly} onCheckedChange={(v) => set("priceDropOnly", v)} label="Uniquement les baisses de prix" />
        </label>
      </Section>

      <Section title="Préférences de score" hint="N'excluent aucune annonce : elles ajustent la pertinence.">
        <Pair>
          <div><Label>Prix idéal (€)</Label><NumberInput value={value.prefs.priceTarget} onValue={(v) => setPref("priceTarget", v)} /></div>
          <div><Label>Surface idéale (m²)</Label><NumberInput value={value.prefs.surfaceTarget} onValue={(v) => setPref("surfaceTarget", v)} /></div>
        </Pair>
        <Pair>
          <div><Label>Chambres idéales</Label><NumberInput value={value.prefs.bedroomsTarget} onValue={(v) => setPref("bedroomsTarget", v)} /></div>
          <div>
            <Label>DPE souhaité</Label>
            <Select value={value.prefs.dpeTarget ?? ""} onChange={(e) => setPref("dpeTarget", (e.target.value || undefined) as DpeClass | undefined)}>
              <option value="">Indifférent</option>
              {DPE_CLASSES.map((c) => <option key={c} value={c}>{c} ou mieux</option>)}
            </Select>
          </div>
        </Pair>
        <label className="flex items-center justify-between gap-3 text-sm">
          <span>Favoriser les annonces récentes</span>
          <Switch checked={value.prefs.freshness} onCheckedChange={(v) => setPref("freshness", v)} label="Favoriser les annonces récentes" />
        </label>
      </Section>

      <Section title="Informations manquantes" hint="Si une annonce ne précise pas une donnée exigée (DPE, équipement…).">
        <Segmented value={value.missingPolicy} onChange={(v) => set("missingPolicy", v)} options={[{ value: "include", label: "Garder « à vérifier »" }, { value: "exclude", label: "Exclure" }]} />
      </Section>
    </div>
  );
}
