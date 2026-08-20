"""Validateur carte bancaire (phase 05).

Un PAN (Primary Account Number) compte de 13 à 19 chiffres et porte une clé de
contrôle Luhn. Le validateur accepte cette plage de longueurs; le chevauchement
avec d'autres identifiants (ex. SIRET à 14 chiffres) relève de l'arbitrage de la
phase 13 et n'est pas traité ici.

Référence: PLAN.md phase 05, PRD §7. Norme: ISO/IEC 7812.
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span
from anonyfy.detect.validators.luhn import is_valid_luhn

__all__ = ["detect", "validate"]

_CB_RE = re.compile(r"(?<!\d)(\d{13,19})(?!\d)")

_CB_RULE = "cb-luhn"


def validate(value: str) -> bool:
    """True si `value` est un PAN (13 à 19 chiffres) à clé Luhn valide."""
    if not (13 <= len(value) <= 19):
        return False
    return is_valid_luhn(value)


def detect(text: str) -> list[Span]:
    """Détecte les cartes bancaires valides dans `text`."""
    spans: list[Span] = []
    for m in _CB_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.CARTE_BANCAIRE,
                    value=candidate,
                    rule_id=_CB_RULE,
                    confidence=1.0,
                )
            )
    return spans