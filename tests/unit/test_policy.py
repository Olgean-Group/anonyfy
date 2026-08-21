"""Politique de fermeture permissive/strict (phase 17, PRD F8).

``policy="permissive"`` (defaut): un span de confiance faible (confidence < 0.8,
non confirme par contexte) est laisse tel quel si non substituable, avec
avertissement journalise (meta uniquement, jamais le clair - invariant 1/D10).
Passe sans lever.

``policy="strict"``: si un span de confiance faible non confirme par contexte
est rencontre, ``mask()`` leve ``UnresolvedSpanError``.

Seuil de confiance pour « faible »: 0.8. Un span avec contextual trigger
(ex: « M. ») a confidence 0.9 (fort); sans trigger, confidence 0.5 (faible).
Ce seuil est interne au mode policy (pas de changement de l'arbitrage phase 13).

Reference: PLAN.md phase 17, criteres 3 et 4. Decision de seuil documentee dans
le rapport final (a valider par l'orchestrateur, D27 ou suivant).
"""

from __future__ import annotations

import json

import pytest

from anonyfy import Vault
from anonyfy.audit import AuditLog
from anonyfy.vault import UnresolvedSpanError

_KEY = b"0" * 16
_SCOPE = "s"


@pytest.fixture
def strict_vault(tmp_path):
    v = Vault(
        key=_KEY,
        scope=_SCOPE,
        policy="strict",
        registry_path=str(tmp_path / "reg.db"),
    )
    yield v
    v.close()


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


class TestStrictLeveSurSpanFaible:
    """Critere 3: en strict, un span faible non confirme par contexte leve.

    « Boulangerie Pierre fait du pain »: « Pierre » est detecte (PRENOM/
    PATRONYME/COMMUNE) avec confidence 0.5 (pas de trigger contextuel fort
    comme « M. », « ne(e) le »). 0.5 < 0.8 -> faible -> strict leve.

    Ce test doit ECHEUER si rien n'est leve (assertRaises).
    """

    def test_strict_leve_sur_pierre_sans_contexte(self, strict_vault):
        with pytest.raises(UnresolvedSpanError):
            strict_vault.mask("Boulangerie Pierre fait du pain")


class TestStrictPasseSurSpanFort:
    """En strict, un span confirme par contexte (confidence >= 0.8) ne leve pas.

    « M. Jean Dupont »: « M. » est un trigger contextuel -> confidence 0.9
    (>= 0.8) -> fort -> strict ne leve pas.
    """

    def test_strict_passe_sur_m_jean_dupont(self, strict_vault):
        m = strict_vault.mask("M. Jean Dupont")
        assert m.text is not None
        assert "Jean" not in m.text


class TestPermissivePasseSansLever:
    """Critere 4: en permissive (defaut), « Boulangerie Pierre » passe sans lever.

    Ce test doit ECHEUER si une exception est levee (assertNoRaise implicite).
    """

    def test_permissive_passe_sur_boulangerie_pierre(self, vault):
        m = vault.mask("Boulangerie Pierre")
        assert m.text is not None
        assert m.text != ""

    def test_permissive_defaut(self, tmp_path):
        """Le defaut est permissive (pas de raise sur span faible)."""
        v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "r.db"))
        m = v.mask("Boulangerie Pierre fait du pain")
        assert m.text is not None
        v.close()


class TestPermissiveAvertissementJournalise:
    """Critere 4 + invariant 1: en permissive avec audit, un avertissement est
    journalise pour les spans faibles, contenant UNIQUEMENT des meta (type,
    confidence, rule_id) - JAMAIS la valeur du span ni le texte clair.
    """

    def test_audit_ne_contient_pas_pierre_en_clair(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        v = Vault(
            key=_KEY,
            scope=_SCOPE,
            audit=AuditLog(log_path),
            registry_path=str(tmp_path / "reg.db"),
        )
        v.mask("Boulangerie Pierre fait du pain")
        v.close()
        content = open(log_path).read()
        # Invariant 1: le clair « Pierre » ne doit JAMAIS figurer dans l'audit.
        assert "Pierre" not in content

    def test_audit_contient_meta_avertissement(self, tmp_path):
        """L'avertissement journalise contient des meta sur les spans faibles
        (entity_type, confidence, rule_id) sans jamais le clair.
        """
        log_path = str(tmp_path / "audit.jsonl")
        v = Vault(
            key=_KEY,
            scope=_SCOPE,
            audit=AuditLog(log_path),
            registry_path=str(tmp_path / "reg.db"),
        )
        v.mask("Boulangerie Pierre fait du pain")
        v.close()
        with open(log_path) as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        assert len(lines) >= 1
        entry = json.loads(lines[0])
        # L'entree contient un champ d'avertissement (meta sur spans faibles).
        assert "weak_spans" in entry
        weak = entry["weak_spans"]
        assert isinstance(weak, list)
        assert len(weak) > 0
        # Chaque avertissement ne contient QUE des meta (pas de valeur claire).
        for w in weak:
            assert "entity_type" in w
            assert "confidence" in w
            assert "rule_id" in w
            # Invariant 1: aucun champ « value » ou texte clair.
            assert "value" not in w
        # Le clair ne figure pas dans l'avertissement serialize.
        assert "Pierre" not in json.dumps(weak, ensure_ascii=False)


class TestPolicyInvalide:
    """Une policy inconnue lève ValueError à la construction."""

    def test_policy_invalide_leve_valueerror(self, tmp_path):
        with pytest.raises(ValueError):
            Vault(
                key=_KEY,
                scope=_SCOPE,
                policy="unknown",
                registry_path=str(tmp_path / "r.db"),
            )
