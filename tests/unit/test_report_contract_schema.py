"""Contrat public de rapport d'observation ``anonyfy.report.v1`` (phase 48).

Valide le schéma normatif packagé dans ``anonyfy.schemas`` :
  - le schéma est un JSON Schema draft 2020-12 valide ;
  - son ``$id`` est l'URN publique attendue par le consommateur privé ;
  - les fixtures agrégées (``report_ok``, ``report_empty``) sont acceptées ;
  - une fixture dérivée de la source (``report_with_clear``: documents,
    filename, excerpt, clear, surrogate) est rejetée.

Référence: ``docs/superpowers/plans/01-anonyfy-public-report-contract.md``
(phase 48, Task 1).
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from anonyfy.schemas import load_report_schema

FIXTURES = Path(__file__).parents[1] / "fixtures" / "report_contract"


def errors(name: str):
    validator = Draft202012Validator(load_report_schema(), format_checker=FormatChecker())
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return list(validator.iter_errors(data))


def test_packaged_schema_is_valid():
    schema = load_report_schema()
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == "urn:anonyfy:report:v1"


@pytest.mark.parametrize("name", ["report_ok.json", "report_empty.json"])
def test_safe_contract_fixtures_are_accepted(name):
    assert errors(name) == []


def test_source_derived_fields_are_rejected():
    assert errors("report_with_clear.json")
