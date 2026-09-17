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

from anonyfy.detect.validators.mod97 import nir_control_key
from anonyfy.types import EntityType, Span

__all__ = ["detect", "format_valid", "validate"]

# Mois NIR valides (phase 64, NIR-CALENDRIER) : 01-12 pour les naissances
# ordinaires, 20 pour les personnes nées en France (numéros spéciaux), 30-31
# pour les personnes nées à l'étranger. INSEE, « NIR - mois de naissance ».
_MOIS_RE = re.compile(r"0[1-9]|1[0-2]|20|3[01]")

# 15 caractères: sexe(1) année(2) mois(2) dept(2) commune(3) rang(3) clé(2).
# Le département accepte 2A, 2B ou deux chiffres. Le mois est large ICI : la
# validation calendaire est portée par ``validate``, car un SUBSTITUT FPE a un
# mois chiffré (aléatoire) qui doit rester plausible (format + clé) sans être un
# mois réel — c'est la propriété F3-type des substituts (test_fpe).
_NIR_FORMAT = re.compile(r"[1-9]\d{2}\d{2}(?:2A|2B|\d{2})\d{3}\d{3}\d{2}")
# Détection: bornes anti-match partiel dans une suite de chiffres plus longue.
_NIR_RE = re.compile(r"(?<!\d)([1-9]\d{2}\d{2}(?:2A|2B|\d{2})\d{3}\d{3}\d{2})(?!\d)")

_NIR_RULE = "nir-mod97"


def format_valid(value: str) -> bool:
    """True si ``value`` a la FORME d'un NIR : 15 caractères, format, clé mod 97.

    Ne vérifie PAS le mois calendaire : un substitut FPE a un mois chiffré et
    doit rester plausible (F3-type « substitut de même type »).
    """
    if len(value) != 15:
        return False
    if _NIR_FORMAT.fullmatch(value) is None:
        return False
    base = value[:13]
    key = value[13:]
    return nir_control_key(base) == int(key)


def validate(value: str) -> bool:
    """True si ``value`` est un NIR réel : forme valide ET mois NIR calendaire.

    Le mois doit être 01-12, 20 (né en France) ou 30-31 (né à l'étranger) ;
    tout autre mois est un faux positif (phase 64, NIR-CALENDRIER). Les
    substituts FPE (mois aléatoire) relèvent de ``format_valid``.
    """
    if not format_valid(value):
        return False
    return _MOIS_RE.fullmatch(value[3:5]) is not None


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
