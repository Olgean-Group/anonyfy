"""Tests du validateur référence de dossier (phase 06).

Logique testée: `ReferenceValidator` accepte une liste de regex fournies par le
client (configurable, PRD §7) et détecte les occurrences dans un texte. La
validation d'une valeur isolée s'appuie sur les patterns fournis.
"""

from __future__ import annotations

import re

import pytest

from anonyfy.detect.validators.reference import ReferenceValidator


class TestReferenceDetect:
    def test_plan_detecte_deux_occurrences(self):
        r = ReferenceValidator(patterns=[r"DOS-\d{6}"])
        spans = r.detect("DOS-123456 et DOS-999999")
        assert len(spans) == 2
        for s in spans:
            assert s.type.value == "REFERENCE_DOSSIER"
            assert s.confidence < 1.0
        assert spans[0].value == "DOS-123456"
        assert spans[1].value == "DOS-999999"

    def test_offsets_corrects(self):
        r = ReferenceValidator(patterns=[r"DOS-\d{6}"])
        spans = r.detect("Ref DOS-123456 fin")
        assert len(spans) == 1
        s = spans[0]
        assert s.start == 4
        assert s.end == 14
        assert s.value == "DOS-123456"

    def test_aucun_span_si_aucun_match(self):
        r = ReferenceValidator(patterns=[r"DOS-\d{6}"])
        assert r.detect("aucune référence ici") == []

    def test_plusieurs_patterns(self):
        r = ReferenceValidator(patterns=[r"DOS-\d{6}", r"REC-\d{4}"])
        spans = r.detect("DOS-123456 et REC-2024")
        assert len(spans) == 2
        valeurs = {s.value for s in spans}
        assert "DOS-123456" in valeurs
        assert "REC-2024" in valeurs

    def test_rule_id_refleche_pattern(self):
        r = ReferenceValidator(patterns=[r"DOS-\d{6}"])
        spans = r.detect("DOS-123456")
        assert spans[0].rule_id.startswith("reference-")

    def test_patterns_vides_ne_detecte_rien(self):
        r = ReferenceValidator(patterns=[])
        assert r.detect("DOS-123456") == []


class TestReferenceValidate:
    def test_valide_si_match_plein(self):
        r = ReferenceValidator(patterns=[r"DOS-\d{6}"])
        assert r.validate("DOS-123456") is True

    def test_invalide_si_aucun_match(self):
        r = ReferenceValidator(patterns=[r"DOS-\d{6}"])
        assert r.validate("DOS-12345") is False
        assert r.validate("XOS-123456") is False

    def test_invalide_match_partiel(self):
        # Une valeur qui ne matche qu'un préfixe n'est pas valide.
        r = ReferenceValidator(patterns=[r"DOS-\d{6}"])
        assert r.validate("DOS-123456X") is False


class TestReferenceConstruction:
    def test_pattern_invalide_leve(self):
        with pytest.raises(re.error):
            ReferenceValidator(patterns=["["])
