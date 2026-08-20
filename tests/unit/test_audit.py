"""Tests du journal d'audit phase 14.

HMAC-SHA-256(key, texte_clair) figé (D3), méta uniquement, jamais le texte
clair OU substitué (D10, OBJ-022).

Référence: PLAN.md phase 14, critères d'acceptation exécutables (6).
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from anonyfy import Vault
from anonyfy.audit import AuditLog

_KEY = b"0" * 16
_SCOPE = "s"


@pytest.fixture
def log_path(tmp_path):
    return str(tmp_path / "audit.jsonl")


@pytest.fixture
def vault(log_path, tmp_path):
    v = Vault(
        key=_KEY,
        scope=_SCOPE,
        audit=AuditLog(log_path),
        registry_path=str(tmp_path / "reg.db"),
    )
    yield v
    v.close()


def _read_log(path: str) -> list[str]:
    with open(path) as f:
        return [line for line in f.read().splitlines() if line.strip()]


class TestPasDeClairDansJournal:
    """Critère 2: aucune valeur claire du corpus n'apparaît dans le journal."""

    def test_jean_dupont_siret_absents_du_journal(self, vault, log_path):
        vault.mask("M. Jean Dupont, SIRET 73282932000033")
        content = open(log_path).read()
        assert "Jean" not in content
        assert "Dupont" not in content
        assert "73282932000033" not in content


class TestNoSubstituteInLog:
    """D10 (OBJ-022): aucun substitut émis n'apparaît dans le journal.

    Le journal ne doit pas constituer un code book partiel.
    """

    def test_no_substitute_in_log(self, vault, log_path):
        text = "M. Jean Dupont, SIRET 73282932000033"
        m = vault.mask(text)
        content = open(log_path).read()
        # Aucun substitut émis ne doit figurer dans le journal
        for ent in m.entities:
            assert ent.value not in content, f"substitut {ent.value!r} fuite dans le journal (D10)"
        # Le texte masqué lui-même ne doit pas figérer non plus
        assert m.text not in content


class TestHmacD3:
    """D3: empreinte HMAC-SHA-256(key, texte_clair), keyée."""

    def test_deux_cles_differentes_empreintes_differentes(self, tmp_path):
        # Même texte, deux clés différentes -> journaux différents
        text = "SIRET 73282932000033"
        p1 = str(tmp_path / "a1.jsonl")
        p2 = str(tmp_path / "a2.jsonl")
        v1 = Vault(
            key=b"0" * 16,
            scope=_SCOPE,
            audit=AuditLog(p1),
            registry_path=str(tmp_path / "r1.db"),
        )
        v2 = Vault(
            key=b"1" * 16,
            scope=_SCOPE,
            audit=AuditLog(p2),
            registry_path=str(tmp_path / "r2.db"),
        )
        v1.mask(text)
        v2.mask(text)
        v1.close()
        v2.close()
        c1 = open(p1).read()
        c2 = open(p2).read()
        assert c1 != c2, "empreintes identiques sous deux clés différentes (D3 violé)"

    def test_deux_textes_differents_meme_cle_empreintes_differentes(self, tmp_path):
        p = str(tmp_path / "a.jsonl")
        v = Vault(
            key=_KEY,
            scope=_SCOPE,
            audit=AuditLog(p),
            registry_path=str(tmp_path / "r.db"),
        )
        v.mask("SIRET 73282932000033")
        v.mask("SIRET 12345678900012")
        v.close()
        lines = _read_log(p)
        assert len(lines) == 2
        e1 = json.loads(lines[0])
        e2 = json.loads(lines[1])
        assert e1["digest"] != e2["digest"], (
            "deux textes différents sous même clé -> empreintes identiques (D3 violé)"
        )

    def test_determinisme_meme_cle_meme_texte_meme_empreinte(self, tmp_path):
        p = str(tmp_path / "a.jsonl")
        v = Vault(
            key=_KEY,
            scope=_SCOPE,
            audit=AuditLog(p),
            registry_path=str(tmp_path / "r.db"),
        )
        v.mask("SIRET 73282932000033")
        v.mask("SIRET 73282932000033")
        v.close()
        lines = _read_log(p)
        e1 = json.loads(lines[0])
        e2 = json.loads(lines[1])
        assert e1["digest"] == e2["digest"], "HMAC non déterministe"


class TestJsonLinesValide:
    """Critère 5: chaque ligne du journal est du JSON parsable."""

    def test_chaque_ligne_json_parsable(self, vault, log_path):
        vault.mask("M. Jean Dupont, SIRET 73282932000033")
        vault.mask("SIRET 12345678900012")
        lines = _read_log(log_path)
        assert len(lines) == 2
        for line in lines:
            json.loads(line)  # lève ValueError si invalide


class TestMetaPresentes:
    """Critère: scope, compte par type, rule_id, empreinte présents."""

    def test_meta_presentes(self, vault, log_path):
        m = vault.mask("M. Jean Dupont, SIRET 73282932000033")
        lines = _read_log(log_path)
        assert len(lines) == 1
        entry = json.loads(lines[0])
        # scope
        assert entry["scope"] == _SCOPE
        # empreinte HMAC présente (hex)
        assert "digest" in entry
        assert isinstance(entry["digest"], str)
        assert len(entry["digest"]) == 64  # SHA-256 hex
        # timestamp présent
        assert "timestamp" in entry
        # compte par type présent
        assert "span_count_by_type" in entry
        # rule_ids présents (ensemble des rule_id des spans)
        assert "rule_ids" in entry
        expected_rules = {ent.rule_id for ent in m.entities}
        assert set(entry["rule_ids"]) == expected_rules
        # compte par type reflète les entités détectées
        expected_counts = Counter(ent.type.value for ent in m.entities)
        assert entry["span_count_by_type"] == dict(expected_counts)


class TestNoAuditNoRegression:
    """Par défaut (audit=None), Vault ne journalise rien (0 régression)."""

    def test_audit_none_comportement_inchangé(self, tmp_path):
        v = Vault(
            key=_KEY,
            scope=_SCOPE,
            registry_path=str(tmp_path / "r.db"),
        )
        m = v.mask("M. Jean Dupont, SIRET 73282932000033")
        assert "Jean" not in m.text
        v.close()
