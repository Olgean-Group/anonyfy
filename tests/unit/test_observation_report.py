"""Accumulateur d'observation agrégat-seul (phase 48, PRD F7/F10).

``ObservationReportBuilder`` consomme les spans retournés par
``Vault.mask(..., observe=True)`` et les réduit IMMÉDIATEMENT à des compteurs
entiers et identifiants contrôlés. Aucun ``Span``, aucune valeur source,
aucun nom de fichier, aucun scope, aucune empreinte de document ne peut
apparaître dans le rapport produit.

Référence: ``docs/superpowers/plans/01-anonyfy-public-report-contract.md``
(phase 48, Task 2).
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from anonyfy.observation_report import ObservationReportBuilder
from anonyfy.schemas import load_report_schema
from anonyfy.types import EntityType, Span

_GAZETTEER_VERSION = "e7adbcf0d3572f3ee97718b68a8a7f4965426b6704c0c604c70861a8f8e85adb"


def span(value: str, entity_type: EntityType, rule_id: str, confidence: float) -> Span:
    return Span(0, len(value), entity_type, value, rule_id, confidence)


def test_builder_reduces_spans_to_safe_aggregates():
    builder = ObservationReportBuilder(confidence_threshold=0.8)
    builder.add_document(
        character_count=30,
        spans=[
            span("Jean Dupont", EntityType.PATRONYME, "gazetteer-nom", 0.5),
            span("73282932000033", EntityType.SIRET, "siret-luhn", 1.0),
        ],
    )
    builder.add_document(
        character_count=20,
        spans=[span("73282932000033", EntityType.SIRET, "siret-luhn", 1.0)],
    )

    report = builder.build(
        generated_at="2026-09-15T10:00:00Z",
        producer_version="0.1.7",
        gazetteer_version=_GAZETTEER_VERSION,
    )

    assert report["schema_version"] == "1.0"
    assert report["producer"] == {"name": "anonyfy", "version": "0.1.7"}
    assert report["generated_at"] == "2026-09-15T10:00:00Z"
    assert report["gazetteer_version"] == _GAZETTEER_VERSION
    assert report["observation"]["mode"] == "observation"
    assert report["observation"]["confidence_threshold"] == 0.8
    assert report["observation"]["document_count"] == 2
    assert report["observation"]["character_count"] == 50
    assert report["observation"]["total_occurrence_count"] == 3
    assert report["observation"]["types"] == [
        {
            "entity_type": "PATRONYME",
            "occurrence_count": 1,
            "document_count": 1,
            "high_confidence_count": 0,
            "low_confidence_count": 1,
            "rule_ids": ["gazetteer-nom"],
        },
        {
            "entity_type": "SIRET",
            "occurrence_count": 2,
            "document_count": 2,
            "high_confidence_count": 2,
            "low_confidence_count": 0,
            "rule_ids": ["siret-luhn"],
        },
    ]
    assert report["observation"]["warnings"] == [
        {"code": "LOW_CONFIDENCE_OCCURRENCES", "count": 1, "entity_type": "PATRONYME"}
    ]

    serialized = json.dumps(report, ensure_ascii=False)
    assert "Jean Dupont" not in serialized
    assert "73282932000033" not in serialized


def _build(builder=None):
    builder = builder or ObservationReportBuilder(confidence_threshold=0.8)
    return builder.build(
        generated_at="2026-09-15T10:00:00Z",
        producer_version="0.1.7",
        gazetteer_version=_GAZETTEER_VERSION,
    )


@pytest.mark.parametrize("threshold", [-0.01, 1.01, -1, 2])
def test_rejects_threshold_outside_unit_interval(threshold):
    with pytest.raises(ValueError):
        ObservationReportBuilder(confidence_threshold=threshold)


def test_rejects_negative_character_count():
    builder = ObservationReportBuilder(confidence_threshold=0.8)
    with pytest.raises(ValueError):
        builder.add_document(character_count=-1, spans=[])


def test_counts_entity_type_once_per_document():
    builder = ObservationReportBuilder(confidence_threshold=0.8)
    builder.add_document(
        character_count=100,
        spans=[
            span("73282932000033", EntityType.SIRET, "siret-luhn", 1.0),
            span("41804261100032", EntityType.SIRET, "siret-luhn", 1.0),
        ],
    )
    types = _build(builder)["observation"]["types"]
    assert types == [
        {
            "entity_type": "SIRET",
            "occurrence_count": 2,
            "document_count": 1,
            "high_confidence_count": 2,
            "low_confidence_count": 0,
            "rule_ids": ["siret-luhn"],
        }
    ]


def test_empty_report_has_zero_totals_and_no_warnings():
    report = _build()
    assert report["observation"]["document_count"] == 0
    assert report["observation"]["character_count"] == 0
    assert report["observation"]["total_occurrence_count"] == 0
    assert report["observation"]["types"] == []
    assert report["observation"]["warnings"] == []


def test_empty_document_emits_empty_documents_warning():
    builder = ObservationReportBuilder(confidence_threshold=0.8)
    builder.add_document(character_count=0, spans=[])
    report = _build(builder)
    assert report["observation"]["warnings"] == [{"code": "EMPTY_DOCUMENTS", "count": 1}]


def test_confidence_equal_to_threshold_counts_as_high():
    builder = ObservationReportBuilder(confidence_threshold=0.8)
    builder.add_document(
        character_count=10,
        spans=[span("Paris", EntityType.COMMUNE, "gazetteer-commune", 0.8)],
    )
    types = _build(builder)["observation"]["types"]
    assert types[0]["high_confidence_count"] == 1
    assert types[0]["low_confidence_count"] == 0


def test_rule_ids_are_sorted_and_unique():
    builder = ObservationReportBuilder(confidence_threshold=0.8)
    builder.add_document(
        character_count=50,
        spans=[
            span("73282932000033", EntityType.SIRET, "siret-luhn", 1.0),
            span("73282932000033", EntityType.SIRET, "siret-luhn", 1.0),
            span("41804261100032", EntityType.SIRET, "autre-regle", 1.0),
        ],
    )
    types = _build(builder)["observation"]["types"]
    assert types[0]["rule_ids"] == ["autre-regle", "siret-luhn"]


def test_report_matches_normative_schema():
    builder = ObservationReportBuilder(confidence_threshold=0.8)
    builder.add_document(
        character_count=30,
        spans=[
            span("Jean Dupont", EntityType.PATRONYME, "gazetteer-nom", 0.5),
            span("73282932000033", EntityType.SIRET, "siret-luhn", 1.0),
        ],
    )
    builder.add_document(character_count=0, spans=[])
    report = _build(builder)
    Draft202012Validator(load_report_schema()).validate(report)
