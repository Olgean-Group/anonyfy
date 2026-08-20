"""Validateur référence de dossier (phase 06).

Les références de dossier n'ont pas de clé de contrôle arithmétique: le client
fournit une liste de regex (configurable, PRD §7 "référence de dossier"). La
détection parcourt le texte et renvoie un span par occurrence validée par au
moins un pattern.

La confiance est de 0.9 (format seul, pas de preuve arithmétique).

Référence: PLAN.md phase 06, PRD §7.
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span

__all__ = ["ReferenceValidator"]

_CONFIDENCE = 0.9


class ReferenceValidator:
    """Validateur de références configuré par une liste de regex.

    Les patterns sont compilés à la construction. Un pattern invalide (syntaxe
    regex incorrecte) lève `re.error` immédiatement.
    """

    __slots__ = ("_patterns", "_compiled")

    def __init__(self, patterns: list[str]) -> None:
        # Compile tôt pour échouer vite sur un pattern invalide.
        self._patterns = list(patterns)
        self._compiled: list[re.Pattern[str]] = [re.compile(p) for p in self._patterns]

    def validate(self, value: str) -> bool:
        """True si `value` correspond intégralement à au moins un pattern."""
        if not value:
            return False
        return any(p.fullmatch(value) is not None for p in self._compiled)

    def detect(self, text: str) -> list[Span]:
        """Détecte les occurrences de référence valides dans `text`."""
        spans: list[Span] = []
        for index, pattern in enumerate(self._compiled):
            rule_id = f"reference-{index}"
            for m in pattern.finditer(text):
                spans.append(
                    Span(
                        start=m.start(),
                        end=m.end(),
                        type=EntityType.REFERENCE_DOSSIER,
                        value=m.group(0),
                        rule_id=rule_id,
                        confidence=_CONFIDENCE,
                    )
                )
        return spans
