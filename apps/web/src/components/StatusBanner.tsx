import { AlertTriangle, CloudOff, FlaskConical, Loader2 } from "lucide-react";
import { useCatalog } from "@/hooks/catalog";
import { formatDate } from "@/lib/format";

/** Informe sur l'état des données : démo fictive, hors ligne, chargement, erreur. */
export function StatusBanner() {
  const { manifest, offline, loading, error, loadedDepartments } = useCatalog();
  return (
    <div className="space-y-2">
      {manifest?.demo && (
        <p className="flex items-start gap-2 rounded-xl bg-accent px-3 py-2 text-xs text-accent-foreground">
          <FlaskConical className="mt-0.5 size-4 shrink-0" />
          <span>Données de démonstration <strong>fictives</strong>. Configurez la source de données réelle dans les paramètres.</span>
        </p>
      )}
      {offline && (
        <p className="flex items-center gap-2 rounded-xl bg-muted px-3 py-2 text-xs text-muted-foreground">
          <CloudOff className="size-4 shrink-0" /> Hors ligne : catalogue du {formatDate(manifest?.generated_at)}.
        </p>
      )}
      {error && (
        <p className="flex items-start gap-2 rounded-xl bg-danger/10 px-3 py-2 text-xs text-danger">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {error}
        </p>
      )}
      {loading && manifest && loadedDepartments.length < manifest.departments.length && (
        <p className="flex items-center gap-2 px-1 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" /> Chargement des départements… ({loadedDepartments.length}/{manifest.departments.length})
        </p>
      )}
    </div>
  );
}
