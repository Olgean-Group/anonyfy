"""Détection des dates textuelles françaises « JJ mois AAAA » (phase 13, D8).

Le validateur phase 06 (``detect/validators/date.py``) couvre le format
``JJ/MM/AAAA``. Ce module étend la détection au format textuel français avec le
mois en toutes lettres (janvier..décembre), en validant la date calendairement
(via ``datetime.date``: 30 février, 29 février non-bissextile, etc. rejetés).

Le ``Span.value`` produit est le texte source « JJ mois AAAA » (forme raw,
cohérent avec le validateur phase 06 qui stocke la raw « JJ/MM/AAAA »). Le
moteur (phase 13) se charge de parser cette valeur pour le masquage.

Confiance 0.9 (format + cohérence calendaire; pas de clé arithmétique).

Référence: PLAN.md phase 13 (D8, détection dates textuelles pré-autorisée D21).
"""

from __future__ import annotations

import datetime
import re

from anonyfy.types import EntityType, Span

__all__ = ["detect", "validate"]

# Mois français -> numéro. Insensible à la casse; les accents sont significatifs.
_MONTHS: dict[str, int] = {
    "janvier": 1,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
}

_MONTHS_ALT = "|".join(_MONTHS)

# JJ (1 ou 2 chiffres) + mois + AAAA (4 chiffres), bornes de mots non-lettre.
# re.IGNORECASE pour accepter « Mars » capitalisé en début de phrase.
_DATE_TEXT_RE = re.compile(
    r"(?<![A-Za-zÀ-ÿ])(\d{1,2}\s+(?:" + _MONTHS_ALT + r")\s+\d{4})(?![A-Za-zÀ-ÿ])",
    re.IGNORECASE,
)

_DATE_RULE = "date-text-fr"
_CONFIDENCE = 0.9


def validate(value: str) -> bool:
    """True si ``value`` est une date textuelle française « JJ mois AAAA » valide."""
    if not value:
        return False
    m = re.fullmatch(r"(\d{1,2})\s+(" + _MONTHS_ALT + r")\s+(\d{4})", value, re.IGNORECASE)
    if m is None:
        return False
    day = int(m.group(1))
    month = _MONTHS[m.group(2).lower()]
    year = int(m.group(3))
    try:
        datetime.date(year, month, day)
    except ValueError:
        return False
    return True


def detect(text: str) -> list[Span]:
    """Détecte les dates textuelles françaises valides dans ``text``."""
    spans: list[Span] = []
    for m in _DATE_TEXT_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.DATE,
                    value=candidate,
                    rule_id=_DATE_RULE,
                    confidence=_CONFIDENCE,
                )
            )
    return spans
