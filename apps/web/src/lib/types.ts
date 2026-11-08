import type { DpeClass, FeatureKey, Listing, PropertyType, TransactionType } from "@findimmo/shared";

/** Exigence pour un équipement : obligatoire (filtre) ou souhaité (score). */
export type FeatureWish = "required" | "preferred";

export interface RadiusFilter {
  lat: number;
  lon: number;
  km: number;
  label: string;
}

/**
 * Critères d'une recherche.
 * - Les champs de la partie « obligatoire » déterminent l'éligibilité.
 * - `prefs` et les équipements « preferred » n'excluent rien : ils influencent le score.
 */
export interface Criteria {
  // ---- obligatoires
  transaction?: TransactionType;
  propertyTypes: PropertyType[];
  departments: string[];
  communes: string[]; // codes INSEE
  postalCodes: string[];
  radius?: RadiusFilter;
  priceMin?: number;
  priceMax?: number;
  surfaceMin?: number;
  surfaceMax?: number;
  landMin?: number;
  roomsMin?: number;
  bedroomsMin?: number;
  dpeMax?: DpeClass; // ex. « D » : A à D acceptés
  features: Partial<Record<FeatureKey, FeatureWish>>;
  keywordsInclude: string[];
  keywordsExclude: string[];
  maxAgeDays?: number;
  priceDropOnly: boolean;
  /** Donnée manquante pour un critère obligatoire : garder l'annonce (« à vérifier ») ou l'exclure. */
  missingPolicy: "include" | "exclude";
  // ---- préférences (score)
  prefs: {
    priceTarget?: number;
    surfaceTarget?: number;
    bedroomsTarget?: number;
    dpeTarget?: DpeClass;
    freshness: boolean;
  };
}

export interface SavedSearch {
  id: string;
  name: string;
  criteria: Criteria;
  active: boolean;
  createdAt: string;
  updatedAt: string;
}

export const FAVORITE_STATUSES = {
  new: "À étudier",
  to_contact: "À contacter",
  contacted: "Contacté",
  visit_planned: "Visite prévue",
  visited: "Visité",
  offer: "Offre faite",
  rejected: "Écarté",
} as const;
export type FavoriteStatus = keyof typeof FAVORITE_STATUSES;

/** Copie minimale de l'annonce, pour conserver un favori même s'il disparaît du catalogue. */
export type ListingSnapshot = Pick<
  Listing,
  "title" | "price" | "city" | "postal_code" | "url" | "image" | "surface" | "property_type" | "transaction"
>;

export interface Favorite {
  listingId: string;
  propertyId?: string;
  addedAt: string;
  updatedAt: string;
  status: FavoriteStatus;
  note: string;
  snapshot: ListingSnapshot;
}

export interface Ignored {
  listingId: string;
  propertyId?: string;
  at: string;
}

export interface SettingRow {
  key: string;
  value: unknown;
}

export interface AlertRead {
  id: string;
  at: string;
}

export type ThemeSetting = "system" | "light" | "dark";

export const emptyCriteria = (): Criteria => ({
  propertyTypes: [],
  departments: [],
  communes: [],
  postalCodes: [],
  features: {},
  keywordsInclude: [],
  keywordsExclude: [],
  priceDropOnly: false,
  missingPolicy: "include",
  prefs: { freshness: true },
});
