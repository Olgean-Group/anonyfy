"""Validateur email (phase 06).

Syntaxe RFC simple: local-part@domaine.tld. La local-part et le domaine sont
sans espaces ni arobase; le domaine comporte au moins un point et une extension.

Pas de clé de contrôle arithmétique: la confiance est de 0.9 (format seul). La
normalisation NFKC/minuscules et la FPE sur la local-part relèvent de la
phase 13 (D9), hors périmètre ici.

Référence: PLAN.md phase 06, PRD §7. Syntaxe: RFC 5321/5322 (sous-ensemble).
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span

__all__ = ["detect", "validate"]

# Local-part: lettres, chiffres, points, tirets, underscores; domaine: étiquettes
# séparées par points; au moins deux étiquettes dont une extension finale.
_EMAIL_FORMAT = re.compile(r"[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._+-])([A-Za-z0-9._+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")

_EMAIL_RULE = "email-format"
_CONFIDENCE = 0.9


def validate(value: str) -> bool:
    """True si `value` est une adresse email au format simple attendu."""
    if not value:
        return False
    return _EMAIL_FORMAT.fullmatch(value) is not None


def detect(text: str) -> list[Span]:
    """Détecte les adresses email valides dans `text`."""
    spans: list[Span] = []
    for m in _EMAIL_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.EMAIL,
                    value=candidate,
                    rule_id=_EMAIL_RULE,
                    confidence=_CONFIDENCE,
                )
            )
    return spans
