/**
 * Contrat de données FindImmo (format publié par le collector, lu par la PWA).
 *
 * Source de vérité : modèles Pydantic `collector/models.py` + `collector/schema.py`.
 * Le JSON Schema correspondant est exporté dans `packages/shared/schema/` (`python -m collector schema`).
 * Toute modification incompatible doit incrémenter FORMAT_VERSION des deux côtés.
 */

export const FORMAT_VERSION = 1;

export type TransactionType = "sale" | "rent";
export type PropertyType = "apartment" | "house" | "land" | "parking" | "commercial" | "building" | "other";
export type ListingStatus = "active" | "unavailable_unconfirmed" | "gone";
/** extracted : donnée structurée de la source ; parsed : lue dans un texte ; computed : calcul exact ; estimated : approximation. */
export type Provenance = "extracted" | "parsed" | "computed" | "estimated";
export type EventType =
  | "new"
  | "price_drop"
  | "price_increase"
  | "features_changed"
  | "unavailable"
  | "reappeared"
  | "gone";

export const FEATURE_KEYS = [
  "garden",
  "terrace",
  "balcony",
  "garage",
  "parking",
  "pool",
  "cellar",
  "elevator",
  "furnished",
] as const;
export type FeatureKey = (typeof FEATURE_KEYS)[number];

export const DPE_CLASSES = ["A", "B", "C", "D", "E", "F", "G"] as const;
export type DpeClass = (typeof DPE_CLASSES)[number];

export interface PricePoint {
  at: string;
  price: number;
}

/** Annonce publiée. Les champs absents sont inconnus (jamais « faux » par défaut). */
export interface Listing {
  id: string;
  source_id: string;
  source_ref: string;
  url: string;
  transaction?: TransactionType;
  property_type?: PropertyType;
  title?: string;
  description?: string;
  price?: number;
  price_per_m2?: number;
  surface?: number;
  land_surface?: number;
  rooms?: number;
  bedrooms?: number;
  city?: string;
  postal_code?: string;
  insee_code?: string;
  department?: string;
  latitude?: number;
  longitude?: number;
  dpe?: DpeClass;
  ges?: DpeClass;
  features?: Partial<Record<FeatureKey, boolean>>;
  /** Provenance des champs non « extracted ». Clés : nom du champ, ou `features.<clé>`. */
  provenance?: Record<string, Provenance>;
  image?: string;
  agency?: string;
  published_at?: string;
  first_seen_at: string;
  last_seen_at: string;
  status: ListingStatus;
  unseen_since?: string;
  price_history: PricePoint[];
  property_id?: string;
  /** Doublons possibles (rapprochement incertain, non fusionné). */
  maybe_same?: string[];
}

export interface ListingEvent {
  id: string;
  type: EventType;
  at: string;
  listing_id: string;
  property_id?: string;
  department?: string;
  old?: unknown;
  new?: unknown;
}

export interface FileRef {
  path: string;
  bytes: number;
  sha256: string;
}

export interface DepartmentEntry extends FileRef {
  code: string;
  name: string;
  region: string;
  count: number;
}

export interface Manifest {
  format_version: number;
  data_version: string;
  generated_at: string;
  demo: boolean;
  total_listings: number;
  departments: DepartmentEntry[];
  files: { events: FileRef; sources: FileRef; report: FileRef; communes?: FileRef };
}

export interface DepartmentFile {
  department: string;
  generated_at: string;
  listings: Listing[];
}

export interface EventsFile {
  generated_at: string;
  events: ListingEvent[];
}

export interface Commune {
  insee: string;
  name: string;
  dep: string;
  cps: string[];
  lat: number | null;
  lon: number | null;
}

export interface SourceInfo {
  id: string;
  name: string;
  domain: string;
  url: string;
  enabled: boolean;
  compatibility: string;
  is_demo: boolean;
  last_success_at: string | null;
  last_status: string | null;
  listings_count: number;
  errors: string[];
}

export const PROPERTY_TYPE_LABELS: Record<PropertyType, string> = {
  apartment: "Appartement",
  house: "Maison",
  land: "Terrain",
  parking: "Parking",
  commercial: "Local / bureau",
  building: "Immeuble",
  other: "Autre",
};

export const FEATURE_LABELS: Record<FeatureKey, string> = {
  garden: "Jardin",
  terrace: "Terrasse",
  balcony: "Balcon",
  garage: "Garage",
  parking: "Parking",
  pool: "Piscine",
  cellar: "Cave",
  elevator: "Ascenseur",
  furnished: "Meublé",
};

export const PROVENANCE_LABELS: Record<Provenance, string> = {
  extracted: "fourni par l'annonce",
  parsed: "lu dans le texte de l'annonce",
  computed: "calculé",
  estimated: "estimé",
};

/** Vérification minimale d'un manifest (le reste du contrat est garanti par le collector). */
export function isManifest(value: unknown): value is Manifest {
  if (typeof value !== "object" || value === null) return false;
  const m = value as Partial<Manifest>;
  return (
    typeof m.format_version === "number" &&
    typeof m.data_version === "string" &&
    Array.isArray(m.departments) &&
    typeof m.files === "object" &&
    m.files !== null
  );
}
