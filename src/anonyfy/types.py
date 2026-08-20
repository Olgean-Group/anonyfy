"""Socle de types du domaine anonyfy (phase 04).

Dataclasses frozen immuables representant les entites detectees, les
substituts, le resultat de masquage, les regles de detection et les entrees
d'audit. Aucune logique de detection/substitution/registre ici: ce module
formalise uniquement les structures de donnees et leurs invariants de
construction.

Reference: PLAN.md phase 04, architecture.md §1 (invariants), PRD §5 (F1/F6).
"""

from __future__ import annotations

import dataclasses
from enum import Enum


class EntityType(Enum):
    """Types d'entite personnels traites par anonyfy (PRD §7)."""

    NIR = "NIR"
    SIREN = "SIREN"
    SIRET = "SIRET"
    IBAN = "IBAN"
    TVA = "TVA"
    CARTE_BANCAIRE = "CARTE_BANCAIRE"
    TELEPHONE = "TELEPHONE"
    PLAQUE_SIV = "PLAQUE_SIV"
    REFERENCE_DOSSIER = "REFERENCE_DOSSIER"
    EMAIL = "EMAIL"
    DATE = "DATE"
    PATRONYME = "PATRONYME"
    PRENOM = "PRENOM"
    COMMUNE = "COMMUNE"
    VOIE = "VOIE"

    @classmethod
    def coerce(cls, value: EntityType | str) -> EntityType:
        """Convertit une chaîne (ou enum) en EntityType; lève ValueError si inconnu."""
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            upper = value.upper()
            for member in cls:
                if member.name == upper or member.value == value:
                    return member
        raise ValueError(f"type d'entite inconnu: {value!r}")


@dataclasses.dataclass(frozen=True)
class Span:
    """Position d'une entite detectee dans un texte.

    Invariants de construction:
      - start >= 0
      - end > start (un span vide n'est pas une entite)
      - 0.0 <= confidence <= 1.0
      - type est un EntityType valide
    """

    start: int
    end: int
    type: EntityType
    value: str
    rule_id: str
    confidence: float

    def __post_init__(self) -> None:
        if not isinstance(self.start, int) or self.start < 0:
            raise ValueError(f"start doit etre un entier >= 0, eu {self.start!r}")
        if not isinstance(self.end, int) or self.end <= self.start:
            raise ValueError(f"end ({self.end!r}) doit etre > start ({self.start!r})")
        # type peut arriver sous forme de str (ergonomie: Span(type='SIRET', ...)).
        if not isinstance(self.type, EntityType):
            object.__setattr__(self, "type", EntityType.coerce(self.type))
        if not isinstance(self.confidence, (int, float)) or isinstance(self.confidence, bool):
            raise ValueError(f"confidence doit etre numerique, eu {self.confidence!r}")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(f"confidence hors [0,1]: {self.confidence!r}")


@dataclasses.dataclass(frozen=True)
class MaskedText:
    """Resultat de Vault.mask: texte substitue et spans des substituts dans .text.

    Les offsets de .entities pointent vers les substituts reels dans .text
    (D15, applique en phase 13).
    """

    text: str
    entities: tuple[Span, ...] = ()


@dataclasses.dataclass(frozen=True)
class Entity:
    """Association d'un span detecte et de son substitut."""

    span: Span
    substitute: str


@dataclasses.dataclass(frozen=True)
class Rule:
    """Regle de detection: identifiant + type d'entite cible."""

    id: str
    type: EntityType

    def __post_init__(self) -> None:
        if not isinstance(self.type, EntityType):
            object.__setattr__(self, "type", EntityType.coerce(self.type))


@dataclasses.dataclass(frozen=True)
class AuditEntry:
    """Entree du journal d'audit (meta uniquement, jamais de texte clair).

    Invariant 1: le clair ne franchit jamais la frontiere. AuditEntry ne porte
    donc que des meta (horodatage, scope, regle, empreinte HMAC, compte) et
    aucun champ libre texte claire ou substitut.
    """

    timestamp: str
    scope: str
    rule_id: str
    digest: str
    span_count: int
    entity_type: EntityType

    def __post_init__(self) -> None:
        if not isinstance(self.entity_type, EntityType):
            object.__setattr__(self, "entity_type", EntityType.coerce(self.entity_type))


__all__ = [
    "AuditEntry",
    "Entity",
    "EntityType",
    "MaskedText",
    "Rule",
    "Span",
]
