"""Validateur NIR (phase 05).

NIR (numéro de sécurité sociale): 13 caractères significatifs (sexe, année,
mois, département, commune, rang) suivis d'une clé de contrôle de 2 chiffres
calculée comme le complément à 97 du reste modulo 97 des 13 caractères.

La Corse utilise les codes départementaux 2A et 2B, substitués respectivement
par 19 et 18 pour le calcul de la clé.

Référence: PLAN.md phase 05, PRD §7. Algorithme: INSEE / décret 2009-1731.
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span
from anonyfy.detect.validators.mod97 import nir_control_key

__all__ = ["detect", "validate"]

# 15 caractères: sexe(1) année(2) mois(2) dept(2) commune(3) rang(3) clé(2).
# Le département accepte 2A, 2B ou deux chiffres.
_NIR_FORMAT = re.compile(r"[1-9]\d{2}\d{2}(?:2A|2B|\d{2})\d{3}\d{3}\d{2}")
# Détection: bornes anti-match partiel dans une suite de chiffres plus longue.
_NIR_RE = re.compile(r"(?<!\d)([1-9]\d{2}\d{2}(?:2A|2B|\d{2})\d{3}\d{3}\d{2})(?!\d)")

_NIR_RULE = "nir-mod97"


def validate(value: str) -> bool:
    """True si `value` est un NIR à 15 caractères dont la clé mod 97 est valide."""
    if len(value) != 15:
        return False
    if _NIR_FORMAT.fullmatch(value) is None:
        return False
    base = value[:13]
    key = value[13:]
    return nir_control_key(base) == int(key)


def detect(text: str) -> list[Span]:
    """Détecte les NIR valides dans `text`."""
    spans: list[Span] = []
    for m in _NIR_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.NIR,
                    value=candidate,
                    rule_id=_NIR_RULE,
                    confidence=1.0,
                )
            )
    return spans