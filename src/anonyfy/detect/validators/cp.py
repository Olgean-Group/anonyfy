"""Validateur code postal français (phase 30, S4).

Détecte les codes postaux français (5 chiffres). La détection brute renvoie
tous les nombres à 5 chiffres; le couplage avec une commune adjacente ou un
déclencheur (``à ``, ``demeurant à ``, ``habite à ``) est géré par
``places.detect`` (OBJ-REC-109): un nombre à 5 chiffres isolé n'est PAS masqué.

Référence: PLAN.md phase 30, PRD §7, OBJ-REC-109.
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span

__all__ = ["detect"]

_CP_RE = re.compile(r"(?<!\d)(\d{5})(?!\d)")

_CP_RULE = "cp-format"


def detect(text: str) -> list[Span]:
    """Détecte tous les nombres à 5 chiffres (codes postaux potentiels).

    Renvoie une liste de ``Span`` (``EntityType.CODE_POSTAL``) avec confiance
    faible (0.5). Le filtrage par couplage (commune adjacente ou déclencheur)
    est du ressort de ``places.detect`` qui émet des spans à confiance élevée.
    """
    spans: list[Span] = []
    for m in _CP_RE.finditer(text):
        candidate = m.group(1)
        spans.append(
            Span(
                start=m.start(1),
                end=m.end(1),
                type=EntityType.CODE_POSTAL,
                value=candidate,
                rule_id=_CP_RULE,
                confidence=0.5,
            )
        )
    return spans
