"""Validateur date (phase 06).

Date au format JJ/MM/AAAA validée calendairement via `datetime.date`: une date
inexistante (31/02, 29/02 non-bissextile, mois 13, jour 32, etc.) est rejetée.

Pas de clé de contrôle arithmétique: la confiance est de 0.9 (format + cohérence
calendaire, mais un tuple JJ/MM/AAAA peut apparaître hors contexte date).

Référence: PLAN.md phase 06, PRD §7. Calendrier grégorien proleptique (datetime).
"""

from __future__ import annotations

import datetime
import re

from anonyfy.types import EntityType, Span

__all__ = ["detect", "validate"]

_DATE_RE = re.compile(r"(?<!\d)(\d{2}/\d{2}/\d{4})(?!\d)")

_DATE_RULE = "date-calendar"
_CONFIDENCE = 0.9


def validate(value: str) -> bool:
    """True si `value` est une date JJ/MM/AAAA calendairement valide."""
    if not value or len(value) != 10 or value[2] != "/" or value[5] != "/":
        return False
    try:
        day, month, year = int(value[0:2]), int(value[3:5]), int(value[6:10])
    except ValueError:
        return False
    try:
        datetime.date(year, month, day)
    except ValueError:
        return False
    return True


def detect(text: str) -> list[Span]:
    """Détecte les dates JJ/MM/AAAA calendaires valides dans `text`."""
    spans: list[Span] = []
    for m in _DATE_RE.finditer(text):
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
