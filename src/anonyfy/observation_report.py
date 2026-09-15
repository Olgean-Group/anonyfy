"""Accumulateur d'observation agrégat-seul (phase 48, PRD F7/F10).

Réduit immédiatement les spans observés à des compteurs entiers et des
identifiants contrôlés. Le module ne conserve ni ``Span``, ni valeur source,
ni nom de fichier, ni scope, ni empreinte: le rapport produit est structurellement
sans donnée dérivée de la source.

Le contrat de sortie est le schéma normatif ``anonyfy.report.v1`` packagé dans
``anonyfy.schemas``.

Référence: ``docs/superpowers/plans/01-anonyfy-public-report-contract.md``
(phase 48, Task 2).
"""

from __future__ import annotations

from collections.abc import Iterable

from anonyfy.types import EntityType, Span

__all__ = ["ObservationReportBuilder"]

# Identifiant de version du contrat (constante du schéma).
_SCHEMA_VERSION = "1.0"
_PRODUCER_NAME = "anonyfy"
_MODE = "observation"


class ObservationReportBuilder:
    """Accumule les observations par document sans retenir aucune valeur source.

    Args:
        confidence_threshold: seuil haut/bas appliqué à chaque span observé.
            Un span de confiance ``>=`` seuil est compté en haute confiance.

    Invariant: seuls des entiers et des identifiants contrôlés sont conservés
    en mémoire (jamais ``Span``, jamais ``.value``).
    """

    def __init__(self, *, confidence_threshold: float) -> None:
        if not 0.0 <= float(confidence_threshold) <= 1.0:
            raise ValueError(
                f"confidence_threshold doit être dans [0, 1], reçu {confidence_threshold!r}"
            )
        self._threshold = float(confidence_threshold)
        self._document_count = 0
        self._character_count = 0
        self._empty_document_count = 0
        self._total_occurrences = 0
        # entity_type -> compteurs entiers
        self._occurrences: dict[EntityType, int] = {}
        self._documents: dict[EntityType, int] = {}
        self._high: dict[EntityType, int] = {}
        self._low: dict[EntityType, int] = {}
        self._rule_ids: dict[EntityType, set[str]] = {}

    def add_document(self, *, character_count: int, spans: Iterable[Span]) -> None:
        """Consomme un document observé et met à jour les agrégats.

        Args:
            character_count: nombre de caractères du document (jamais le texte).
            spans: spans détectés par ``Vault.mask(..., observe=True)``.

        Lève ``ValueError`` pour un compte de caractères négatif.
        """
        if not isinstance(character_count, int) or isinstance(character_count, bool):
            raise ValueError(f"character_count doit être un entier, reçu {character_count!r}")
        if character_count < 0:
            raise ValueError(f"character_count doit être >= 0, reçu {character_count!r}")

        self._document_count += 1
        self._character_count += character_count
        if character_count == 0:
            self._empty_document_count += 1

        seen_types: set[EntityType] = set()
        for span in spans:
            entity_type = span.type
            self._total_occurrences += 1
            self._occurrences[entity_type] = self._occurrences.get(entity_type, 0) + 1
            self._rule_ids.setdefault(entity_type, set()).add(span.rule_id)
            if span.confidence >= self._threshold:
                self._high[entity_type] = self._high.get(entity_type, 0) + 1
            else:
                self._low[entity_type] = self._low.get(entity_type, 0) + 1
            if entity_type not in seen_types:
                seen_types.add(entity_type)
                self._documents[entity_type] = self._documents.get(entity_type, 0) + 1

    def build(
        self,
        *,
        generated_at: str,
        producer_version: str,
        gazetteer_version: str,
    ) -> dict[str, object]:
        """Construit le rapport conforme à ``anonyfy.report.v1``.

        Les listes sont triées (types par ``entity_type``, règles lexicalement).
        ``LOW_CONFIDENCE_OCCURRENCES`` n'est émis que si son compte est positif;
        ``EMPTY_DOCUMENTS`` n'est émis que si au moins un document est vide.
        """
        types = [
            {
                "entity_type": entity_type.value,
                "occurrence_count": self._occurrences[entity_type],
                "document_count": self._documents[entity_type],
                "high_confidence_count": self._high.get(entity_type, 0),
                "low_confidence_count": self._low.get(entity_type, 0),
                "rule_ids": sorted(self._rule_ids[entity_type]),
            }
            for entity_type in sorted(self._occurrences, key=lambda item: item.value)
        ]

        warnings: list[dict[str, object]] = []
        for entity_type in sorted(self._occurrences, key=lambda item: item.value):
            low_count = self._low.get(entity_type, 0)
            if low_count > 0:
                warnings.append(
                    {
                        "code": "LOW_CONFIDENCE_OCCURRENCES",
                        "count": low_count,
                        "entity_type": entity_type.value,
                    }
                )
        if self._empty_document_count > 0:
            warnings.append({"code": "EMPTY_DOCUMENTS", "count": self._empty_document_count})

        return {
            "schema_version": _SCHEMA_VERSION,
            "producer": {"name": _PRODUCER_NAME, "version": producer_version},
            "generated_at": generated_at,
            "observation": {
                "mode": _MODE,
                "confidence_threshold": self._threshold,
                "document_count": self._document_count,
                "character_count": self._character_count,
                "total_occurrence_count": self._total_occurrences,
                "types": types,
                "warnings": warnings,
            },
            "gazetteer_version": gazetteer_version,
        }
