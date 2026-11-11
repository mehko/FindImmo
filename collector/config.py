"""Chargement de la configuration (départements, sources) depuis ``config/``."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


class Department(BaseModel):
    code: str
    name: str
    region: str


class Compatibility(StrEnum):
    COMPATIBLE = "compatible"  # vérifié : extraction fonctionnelle et autorisée par robots.txt
    PARTIAL = "partial"  # fonctionne avec des données incomplètes
    PENDING_VALIDATION = "pending_validation"  # découverte, à valider avant activation
    BLOCKED = "blocked"  # protection anti-bot ou robots.txt interdisant l'accès
    INCOMPATIBLE = "incompatible"  # pas de méthode d'extraction viable
    FIXTURE = "fixture"  # données fictives de démonstration / test


class PublishPolicy(BaseModel):
    image: bool = True  # lien vers une vignette hébergée par la source (pas de copie)
    description_chars: int = 280  # extrait publié ; 0 pour ne rien publier


class SourceConfig(BaseModel):
    id: str
    name: str
    domain: str
    url: str
    cms: str | None = None
    network: str | None = None
    departments: list[str] = Field(default_factory=list)  # vide = tous les départements configurés
    method: str  # sitemap_jsonld | html | feed | adapter
    adapter: str | None = None  # nom d'adaptateur réutilisable (ex. "laforet")
    enabled: bool = False
    compatibility: Compatibility = Compatibility.PENDING_VALIDATION
    render: str | None = None  # "playwright" si la page nécessite JavaScript (et l'autorise)
    rate_limit_seconds: float = 1.5
    max_details_per_run: int = 250
    max_run_seconds: int = 900
    refresh_days: float = 3.0
    # Les booléens « false » des sources sont souvent des valeurs par défaut non renseignées.
    # Par défaut ils sont donc traités comme « inconnu » ; activer seulement si la source est fiable.
    trust_false_features: bool = False
    is_demo: bool = False
    options: dict[str, Any] = Field(default_factory=dict)
    publish: PublishPolicy = Field(default_factory=PublishPolicy)
    # Mention de source affichée avec chaque annonce (ex. « Source : Figaro Immobilier »), exigée par certains accords.
    attribution: str | None = None
    # Ne pas publier les annonces qui ne sont plus « actives » (retrait de la source à répercuter rapidement).
    hide_unavailable: bool = False
    notes: str | None = None


class Settings(BaseModel):
    user_agent: str = "FindImmoBot/0.1 (+https://github.com/mehko/FindImmo; usage personnel)"
    gone_after_days: float = 7.0
    gone_after_misses: int = 3
    prune_gone_after_days: float = 30.0
    events_retention_days: int = 120
    published_events_days: int = 60


def _load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_departments(config_dir: Path = CONFIG_DIR) -> list[Department]:
    data = _load_yaml(config_dir / "departments.yaml")
    return [Department.model_validate(d) for d in data.get("departments", [])]


def load_sources(config_dir: Path = CONFIG_DIR, include_candidates: bool = False) -> list[SourceConfig]:
    files = [config_dir / "sources.yaml"]
    if include_candidates and (config_dir / "sources.candidates.yaml").exists():
        files.append(config_dir / "sources.candidates.yaml")
    sources: list[SourceConfig] = []
    seen: set[str] = set()
    for f in files:
        if not f.exists():
            continue
        for item in _load_yaml(f).get("sources", []) or []:
            src = SourceConfig.model_validate(item)
            if src.id in seen:
                raise ValueError(f"Identifiant de source dupliqué : {src.id}")
            seen.add(src.id)
            sources.append(src)
    return sources


def load_settings(config_dir: Path = CONFIG_DIR) -> Settings:
    path = config_dir / "settings.yaml"
    return Settings.model_validate(_load_yaml(path)) if path.exists() else Settings()
