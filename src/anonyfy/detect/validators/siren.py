"""Validateur SIREN et SIRET (phase 05).

SIREN: 9 chiffres à clé de contrôle Luhn valide.
SIRET: 14 chiffres (SIREN + NIC) à clé de contrôle Luhn valide.

`detect(text)` parcourt le texte à la recherche de suites de chiffres respectant
la longueur et la clé Luhn; un nombre de 14 chiffres dont la clé est fausse ne
produit aucun span (mitigation du risque PLAN "tout 14 chiffres = SIRET").

Référence: PLAN.md phase 05, PRD §7.
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span
from anonyfy.detect.validators.luhn import is_valid_luhn

__all__ = ["detect", "detect_siret", "validate", "validate_siret"]

_SIREN_RE = re.compile(r"(?<!\d)(\d{9})(?!\d)")
_SIRET_RE = re.compile(r"(?<!\d)(\d{14})(?!\d)")

_SIREN_RULE = "siren-luhn"
_SIRET_RULE = "siret-luhn"


def validate(value: str) -> bool:
    """True si `value` est un SIREN (9 chiffres) à clé Luhn valide."""
    if len(value) != 9:
        return False
    return is_valid_luhn(value)


def validate_siret(value: str) -> bool:
    """True si `value` est un SIRET (14 chiffres) à clé Luhn valide."""
    if len(value) != 14:
        return False
    return is_valid_luhn(value)


def detect(text: str) -> list[Span]:
    """Détecte les SIREN valides dans `text`."""
    spans: list[Span] = []
    for m in _SIREN_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.SIREN,
                    value=candidate,
                    rule_id=_SIREN_RULE,
                    confidence=1.0,
                )
            )
    return spans


def detect_siret(text: str) -> list[Span]:
    """Détecte les SIRET valides dans `text`."""
    spans: list[Span] = []
    for m in _SIRET_RE.finditer(text):
        candidate = m.group(1)
        if validate_siret(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.SIRET,
                    value=candidate,
                    rule_id=_SIRET_RULE,
                    confidence=1.0,
                )
            )
    return spans