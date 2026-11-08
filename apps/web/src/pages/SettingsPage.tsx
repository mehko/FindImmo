import { useLiveQuery } from "dexie-react-hooks";
import { Download, RefreshCw, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Chip, Segmented } from "@/components/ui/chip";
import { Input, Label } from "@/components/ui/input";
import { useCatalog } from "@/hooks/catalog";
import { useSetting } from "@/hooks/personal";
import { applyTheme } from "@/lib/theme";
import { BackupError, exportBackup, importBackup } from "@/lib/backup";
import { defaultDataUrl } from "@/lib/catalog";
import { db } from "@/lib/db";
import { formatDate } from "@/lib/format";
import type { ThemeSetting } from "@/lib/types";

export function SettingsPage() {
  const { manifest, sources, reload, loading, dataUrl, offline } = useCatalog();
  const [theme, setTheme] = useSetting<ThemeSetting>("theme", "system");
  const [url, setUrl] = useSetting<string>("dataUrl", "");
  const [deps, setDeps] = useSetting<string[] | null>("departments", null);
  const [draftUrl, setDraftUrl] = useState<string | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const counts = useLiveQuery(async () => ({ s: await db.searches.count(), f: await db.favorites.count(), i: await db.ignored.count() }), [], { s: 0, f: 0, i: 0 });

  const changeTheme = (t: ThemeSetting) => {
    void setTheme(t);
    applyTheme(t);
  };
  const doExport = async () => {
    const backup = await exportBackup();
    const blob = new Blob([JSON.stringify(backup, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `findimmo-sauvegarde-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const doImport = async (file: File) => {
    try {
      const data: unknown = JSON.parse(await file.text());
      const replace = confirm("Remplacer toutes vos données actuelles ?\nOK = remplacer · Annuler = fusionner");
      const s = await importBackup(data, replace ? "replace" : "merge");
      setMessage({ ok: true, text: `Import réussi : ${s.searches} recherche(s), ${s.favorites} favori(s), ${s.ignored} bien(s) ignoré(s).` });
    } catch (err) {
      setMessage({ ok: false, text: err instanceof BackupError ? err.message : err instanceof SyntaxError ? "Fichier JSON illisible." : String(err) });
    }
  };
  const allDeps = manifest?.departments ?? [];
  const selected = deps ?? allDeps.map((d) => d.code);
  const toggleDep = (code: string) => {
    const next = selected.includes(code) ? selected.filter((c) => c !== code) : [...selected, code];
    void setDeps(next.length === allDeps.length ? null : next);
  };

  return (
    <>
      <TopBar back title="Paramètres" />
      <main className="mx-auto max-w-xl space-y-3 px-4 pb-16">
        <Card className="space-y-3 p-4">
          <h2 className="text-sm font-semibold">Apparence</h2>
          <Segmented value={theme} onChange={changeTheme} options={[{ value: "system", label: "Système" }, { value: "light", label: "Clair" }, { value: "dark", label: "Sombre" }]} />
        </Card>

        <Card className="space-y-3 p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Catalogue</h2>
            <Button variant="ghost" size="sm" onClick={reload} disabled={loading}><RefreshCw className={loading ? "animate-spin" : ""} /> Actualiser</Button>
          </div>
          <dl className="grid grid-cols-2 gap-y-1 text-sm">
            <dt className="text-muted-foreground">Mise à jour</dt><dd>{formatDate(manifest?.generated_at)} {offline && <Badge variant="muted">hors ligne</Badge>}</dd>
            <dt className="text-muted-foreground">Annonces</dt><dd>{manifest?.total_listings ?? "—"} {manifest?.demo && <Badge variant="accent">démo fictive</Badge>}</dd>
            <dt className="text-muted-foreground">Version</dt><dd className="font-mono text-xs">{manifest?.data_version ?? "—"}</dd>
          </dl>
          <div>
            <Label>Départements à télécharger</Label>
            <div className="flex flex-wrap gap-2">
              {allDeps.map((d) => <Chip key={d.code} active={selected.includes(d.code)} onClick={() => toggleDep(d.code)}>{d.code} · {d.count}</Chip>)}
            </div>
          </div>
          <div>
            <Label htmlFor="data-url">Adresse des données (GitHub Pages)</Label>
            <Input id="data-url" value={draftUrl ?? url} placeholder={defaultDataUrl()} onChange={(e) => setDraftUrl(e.target.value)} inputMode="url" />
            <p className="mt-1 text-xs text-muted-foreground">Actuelle : {dataUrl}</p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" disabled={draftUrl === null} onClick={() => { void setUrl((draftUrl ?? "").trim()); setDraftUrl(null); }}>Enregistrer</Button>
              {url && <Button size="sm" variant="ghost" onClick={() => void setUrl("")}>Par défaut</Button>}
            </div>
          </div>
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => void db.catalogFiles.clear().then(reload)}><Trash2 /> Vider le cache du catalogue</Button>
        </Card>

        <Card className="space-y-3 p-4">
          <h2 className="text-sm font-semibold">Mes données (sur cet appareil uniquement)</h2>
          <p className="text-sm text-muted-foreground">{counts.s} recherche(s) · {counts.f} favori(s) · {counts.i} bien(s) ignoré(s). Aucune synchronisation : exportez pour sauvegarder ou transférer vers l'autre téléphone.</p>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="outline" onClick={() => void doExport()}><Download /> Exporter</Button>
            <Button variant="outline" onClick={() => fileRef.current?.click()}><Upload /> Importer</Button>
          </div>
          <input ref={fileRef} type="file" accept="application/json,.json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void doImport(f); e.target.value = ""; }} />
          {message && <p className={message.ok ? "text-sm text-success" : "text-sm text-danger"}>{message.text}</p>}
        </Card>

        <Card className="space-y-2 p-4">
          <h2 className="text-sm font-semibold">Sources</h2>
          <ul className="divide-y text-sm">
            {sources.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <p className="truncate font-medium">{s.name}</p>
                  <p className="text-xs text-muted-foreground">{s.enabled ? `${s.listings_count} annonces · ${s.last_success_at ? `OK le ${formatDate(s.last_success_at)}` : "jamais collectée"}` : s.compatibility}</p>
                </div>
                <Badge variant={!s.enabled ? "muted" : s.last_status === "ok" ? "success" : s.last_status === "error" ? "danger" : "warning"}>{s.enabled ? (s.last_status ?? "—") : "inactive"}</Badge>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">FindImmo ne couvre que les sources intégrées : ce n'est pas une vue exhaustive du marché.</p>
        </Card>
      </main>
    </>
  );
}
