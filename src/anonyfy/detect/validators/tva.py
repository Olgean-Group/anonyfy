"""Validateur TVA intracommunautaire FR (phase 05).

Format: "FR" + 2 chiffres de clé + 9 chiffres de SIREN (13 caractères).
Clé = (12 + 3 * (SIREN mod 97)) mod 97.

Référence: PLAN.md phase 05, PRD §7. Formule: DGFiP / VIES.
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span

__all__ = ["detect", "validate"]

_TVA_FORMAT = re.compile(r"FR(\d{2})(\d{9})")
_TVA_RE = re.compile(r"(?<![A-Za-z0-9])(FR\d{2}\d{9})(?![A-Za-z0-9])")

_TVA_RULE = "tva-fr-key"


def _expected_key(siren: str) -> int:
    return (12 + 3 * (int(siren) % 97)) % 97


def validate(value: str) -> bool:
    """True si `value` est un numéro TVA FR (13 caractères) à clé valide."""
    if len(value) != 13:
        return False
    m = _TVA_FORMAT.fullmatch(value)
    if m is None:
        return False
    key_str, siren = m.group(1), m.group(2)
    return _expected_key(siren) == int(key_str)


def detect(text: str) -> list[Span]:
    """Détecte les numéros TVA FR valides dans `text`."""
    spans: list[Span] = []
    for m in _TVA_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.TVA,
                    value=candidate,
                    rule_id=_TVA_RULE,
                    confidence=1.0,
                )
            )
    return spans