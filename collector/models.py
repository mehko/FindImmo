"""Modèles de données du collector.

Trois niveaux :

* ``RawListing``  : ce qu'un connecteur extrait d'une source, sans interprétation.
* ``Listing``     : annonce normalisée, avec provenance par champ et suivi temporel.
* ``ListingEvent``: changement significatif (nouveauté, prix, disponibilité…).

Règle d'or : une information absente reste ``None``. On n'invente jamais de caractéristique.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Version du format JSON publié (manifest + fichiers). À incrémenter en cas de changement incompatible.
FORMAT_VERSION = 1


class TransactionType(StrEnum):
    SALE = "sale"
    RENT = "rent"


class PropertyType(StrEnum):
    APARTMENT = "apartment"
    HOUSE = "house"
    LAND = "land"
    PARKING = "parking"
    COMMERCIAL = "commercial"
    BUILDING = "building"
    OTHER = "other"


class ListingStatus(StrEnum):
    ACTIVE = "active"
    # Non retrouvée lors d'une collecte réussie : ni vendue, ni supprimée tant que non confirmé.
    UNAVAILABLE_UNCONFIRMED = "unavailable_unconfirmed"
    # Absente depuis longtemps (seuil configurable) : retirée probable.
    GONE = "gone"


class Provenance(StrEnum):
    EXTRACTED = "extracted"  # champ structuré fourni par la source (JSON-LD, dataLayer, flux)
    PARSED = "parsed"  # déduit par analyse du texte de la source (titre, description, liste HTML)
    COMPUTED = "computed"  # calculé de façon exacte (prix/m², département depuis le code postal)
    ESTIMATED = "estimated"  # approximation (coordonnées du centre de la commune)


class EventType(StrEnum):
    NEW = "new"
    PRICE_DROP = "price_drop"
    PRICE_INCREASE = "price_increase"
    FEATURES_CHANGED = "features_changed"
    UNAVAILABLE = "unavailable"
    REAPPEARED = "reappeared"
    GONE = "gone"


# Équipements reconnus. Une clé absente du dict ``features`` signifie « information inconnue ».
FEATURE_KEYS: tuple[str, ...] = (
    "garden",
    "terrace",
    "balcony",
    "garage",
    "parking",
    "pool",
    "cellar",
    "elevator",
    "furnished",
)

DPE_CLASSES = ("A", "B", "C", "D", "E", "F", "G")


class RawListing(BaseModel):
    """Annonce telle qu'extraite d'une source. Valeurs brutes, toutes optionnelles sauf l'identité."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_ref: str
    url: str
    title: str | None = None
    description: str | None = None
    transaction: str | None = None
    property_type: str | None = None
    price: float | None = None
    surface: float | None = None
    land_surface: float | None = None
    rooms: int | None = None
    bedrooms: int | None = None
    city: str | None = None
    postal_code: str | None = None
    insee_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    dpe: str | None = None
    ges: str | None = None
    # Valeurs explicitement déclarées par la source (True/False). Voir ``trust_false_features``.
    features: dict[str, bool] = Field(default_factory=dict)
    published_at: str | None = None
    image: str | None = None
    agency: str | None = None
    # Champs dont la valeur a été obtenue par analyse de texte plutôt que par une donnée structurée.
    parsed_fields: list[str] = Field(default_factory=list)


class ListingRef(BaseModel):
    """Référence découverte (ex. URL de sitemap) avant récupération du détail."""

    source_id: str
    source_ref: str
    url: str
    lastmod: str | None = None
    postal_code_hint: str | None = None
    department_hint: str | None = None
    # Certains connecteurs (flux, pages de liste riches) fournissent directement l'annonce complète.
    raw: RawListing | None = None


class PricePoint(BaseModel):
    at: str
    price: float


class Listing(BaseModel):
    """Annonce normalisée et suivie dans le temps."""

    id: str
    source_id: str
    source_ref: str
    url: str
    transaction: TransactionType | None = None
    property_type: PropertyType | None = None
    title: str | None = None
    description: str | None = None
    price: float | None = None
    price_per_m2: float | None = None
    surface: float | None = None
    land_surface: float | None = None
    rooms: int | None = None
    bedrooms: int | None = None
    city: str | None = None
    postal_code: str | None = None
    insee_code: str | None = None
    department: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    dpe: str | None = None
    ges: str | None = None
    features: dict[str, bool] = Field(default_factory=dict)
    # Provenance des champs non nuls lorsqu'elle n'est pas « extracted » (valeur par défaut implicite).
    provenance: dict[str, Provenance] = Field(default_factory=dict)
    image: str | None = None
    agency: str | None = None
    published_at: str | None = None
    first_seen_at: str
    last_seen_at: str
    last_fetched_at: str | None = None
    status: ListingStatus = ListingStatus.ACTIVE
    unseen_count: int = 0
    unseen_since: str | None = None
    price_history: list[PricePoint] = Field(default_factory=list)
    property_id: str | None = None
    is_demo: bool = False


class ListingEvent(BaseModel):
    id: str
    type: EventType
    at: str
    listing_id: str
    property_id: str | None = None
    department: str | None = None
    old: Any = None
    new: Any = None


class DuplicateCandidate(BaseModel):
    """Correspondance incertaine : affichée comme « doublon possible », jamais fusionnée automatiquement."""

    a: str
    b: str
    score: float
    reasons: list[str]


class PropertyGroup(BaseModel):
    id: str
    listing_ids: list[str]
    confidence: float
    level: int  # 1 = URL/identifiant, 2/3 = rapprochement par caractéristiques (score)


class SourceRunStatus(BaseModel):
    """Résultat d'une collecte pour une source (produit par ``collect``, consommé par ``process``)."""

    source_id: str
    started_at: str
    finished_at: str | None = None
    ok: bool = False
    # Vrai seulement si la découverte a été exhaustive : condition pour marquer des annonces absentes.
    discovery_complete: bool = False
    refs_discovered: int = 0
    refs_in_scope: int = 0
    details_fetched: int = 0
    details_failed: int = 0
    removed: int = 0  # pages détail supprimées ou redirigées (annonces retirées)
    backlog: int = 0
    errors: list[str] = Field(default_factory=list)


class SourceBatch(BaseModel):
    """Sortie de ``collect`` pour une source : références vues + annonces brutes récupérées."""

    status: SourceRunStatus
    seen_refs: list[str] = Field(default_factory=list)
    listings: list[RawListing] = Field(default_factory=list)
    out_of_scope_refs: list[str] = Field(default_factory=list)
    removed_refs: list[str] = Field(default_factory=list)
    lastmods: dict[str, str] = Field(default_factory=dict)
