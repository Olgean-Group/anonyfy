"""Validateur IBAN France (phase 05).

Un IBAN français compte 27 caractères: "FR" + 2 chiffres de clé + 23 chiffres
de BBAN. La validation mod 97 déplace les 4 premiers caractères en fin de
chaîne, convertit les lettres (A=10 ... Z=35) et exige un reste de 1.

Référence: PLAN.md phase 05, PRD §7. Norme: ISO 13616 / EBS204.
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span
from anonyfy.detect.validators.mod97 import iban_mod97

__all__ = ["detect", "validate"]

_IBAN_FORMAT = re.compile(r"FR\d{25}")
_IBAN_RE = re.compile(r"(?<![A-Za-z0-9])(FR\d{25})(?![A-Za-z0-9])")

_IBAN_RULE = "iban-mod97"


def validate(value: str) -> bool:
    """True si `value` est un IBAN français (27 caractères) à clé mod 97 valide."""
    if len(value) != 27:
        return False
    if _IBAN_FORMAT.fullmatch(value) is None:
        return False
    return iban_mod97(value) == 1


def detect(text: str) -> list[Span]:
    """Détecte les IBAN FR valides dans `text`."""
    spans: list[Span] = []
    for m in _IBAN_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.IBAN,
                    value=candidate,
                    rule_id=_IBAN_RULE,
                    confidence=1.0,
                )
            )
    return spans