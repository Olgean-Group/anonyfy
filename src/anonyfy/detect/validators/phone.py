"""Validateur téléphone FR (phase 06).

Plan de numérotation français:
  - national: 10 chiffres commençant par 0 + chiffre valide FR (0[1-9]\\d{8});
  - international: +33 suivi de 9 chiffres (le 0 initial est supprimé).

Pas de clé de contrôle arithmétique: la confiance est de 0.9 (format seul).
La mitigation du risque PLAN "tout numéro à 10 chiffres" s'appuie sur le préfixe
exigé: un numéro ne commençant ni par 0+[1-9] ni par +33[1-9] est rejeté.

Référence: PLAN.md phase 06, PRD §7. Plan de numérotation: ARCEP.
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span

__all__ = ["detect", "validate"]

# National: 0 + chiffre 1-9 + 8 chiffres. International: +33 + 9 chiffres (sans 0).
_PHONE_FORMAT = re.compile(r"(?:0[1-9]\d{8}|\+33[1-9]\d{8})")
_PHONE_RE = re.compile(r"(?<![\d+])(0[1-9]\d{8}|\+33[1-9]\d{8})(?!\d)")

_PHONE_RULE = "phone-format"
_CONFIDENCE = 0.9


def validate(value: str) -> bool:
    """True si `value` est un numéro de téléphone FR au format attendu."""
    if not value:
        return False
    return _PHONE_FORMAT.fullmatch(value) is not None


def detect(text: str) -> list[Span]:
    """Détecte les numéros de téléphone FR valides dans `text`."""
    spans: list[Span] = []
    for m in _PHONE_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.TELEPHONE,
                    value=candidate,
                    rule_id=_PHONE_RULE,
                    confidence=_CONFIDENCE,
                )
            )
    return spans
