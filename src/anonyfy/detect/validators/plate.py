"""Validateur plaque SIV (phase 06).

Format SIV (depuis 2009): LL-NNN-LL[L] (2 lettres, tiret, 3 chiffres, tiret,
2 ou 3 lettres). Les lettres I, O, U sont exclues (confusion avec 1, 0, V); la
séquence SS est exclue comme préfixe (historique).

Pas de clé de contrôle arithmétique: la confiance est de 0.9 (format seul).

Référence: PLAN.md phase 06, PRD §7. SIV: décret 2009-136.
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span

__all__ = ["detect", "validate"]

# Lettres autorisées: A-H, J-N, P-T, V-Z (exclut I, O, U).
_letters = "A-HJ-NP-TV-Z"
_PLATE_FORMAT = re.compile(rf"(?!SS)[{_letters}]{{2}}-\d{{3}}-[{_letters}]{{2,3}}")
_PLATE_RE = re.compile(
    rf"(?<![A-Za-z0-9-])((?!SS)[{_letters}]{{2}}-\d{{3}}-[{_letters}]{{2,3}})(?![A-Za-z0-9-])"
)

_PLATE_RULE = "plate-siv-format"
_CONFIDENCE = 0.9


def validate(value: str) -> bool:
    """True si `value` est une plaque SIV au format attendu."""
    if not value:
        return False
    return _PLATE_FORMAT.fullmatch(value) is not None


def detect(text: str) -> list[Span]:
    """Détecte les plaques SIV valides dans `text`."""
    spans: list[Span] = []
    for m in _PLATE_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.PLAQUE_SIV,
                    value=candidate,
                    rule_id=_PLATE_RULE,
                    confidence=_CONFIDENCE,
                )
            )
    return spans
