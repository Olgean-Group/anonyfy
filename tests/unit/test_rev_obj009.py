"""Phase 57 — OBJ-009 : double détection dans ``Vault.mask``.

``Vault.mask`` appelait ``self._engine.detect(text)`` (contrôle de policy) PUIS
``self._engine.mask(text)`` (qui re-détecte via ``_detect_all_with_format``).
La détection coûtait ~36 % du temps de ``mask()`` sur un texte dense (mesure :
37,6 ms de détection pour 104 ms de masquage) et était parcourue DEUX fois.

Le résultat de ``detect()`` n'est utilisé que pour :

- ``policy="strict"`` : lever ``UnresolvedSpanError`` sur un span faible ;
- journal d'audit : métadonnées ``weak_spans``.

Dans le chemin par défaut (permissive, sans audit), il est inutile. Les tests
ci-dessous verrouillent l'absence de double détection sur ce chemin, la
préservation du comportement strict et la préservation des ``weak_spans``.

Référence: BACKLOG OBJ-009.
"""

from __future__ import annotations

import json

import pytest

from anonyfy import Vault
from anonyfy.audit import AuditLog
from anonyfy.surrogate.engine import Engine
from anonyfy.vault import UnresolvedSpanError

KEY = b"0" * 16


@pytest.fixture
def detect_calls(monkeypatch):
    """Compte les appels à ``Engine.detect`` (la détection redondante)."""
    compteur = {"n": 0}
    original = Engine.detect

    def compte(self, text):
        compteur["n"] += 1
        return original(self, text)

    monkeypatch.setattr(Engine, "detect", compte)
    return compteur


@pytest.fixture
def mask_calls(monkeypatch):
    """Compte les appels à ``Engine.mask`` (le chemin de substitution)."""
    compteur = {"n": 0}
    original = Engine.mask

    def compte(self, text, **kwargs):
        compteur["n"] += 1
        return original(self, text, **kwargs)

    monkeypatch.setattr(Engine, "mask", compte)
    return compteur


class TestSimpleDetectionCheminDefaut:
    """Permissive sans audit : une seule détection (celle du masquage)."""

    def test_mask_permissive_sans_audit_ne_detecte_pas_deux_fois(
        self, tmp_path, detect_calls, mask_calls
    ):
        v = Vault(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        try:
            v.mask("SIRET 73282932000033 et M. Jean Dupont demeure à Paris.")
            assert mask_calls["n"] == 1, "le chemin de substitution doit être appelé une fois"
            assert detect_calls["n"] == 0, (
                f"detect() ne doit pas être appelé sur le chemin par défaut "
                f"({detect_calls['n']} appels redondants)"
            )
        finally:
            v.close()

    def test_mask_observe_ne_detecte_pas_non_plus(self, tmp_path, detect_calls):
        v = Vault(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        try:
            v.mask("SIRET 73282932000033", observe=True)
            assert detect_calls["n"] == 0, "observe utilise Engine.mask(observe=True), pas detect()"
        finally:
            v.close()


class TestDetectionConserveeQuandNecessaire:
    """Strict et audit gardent le contrôle préalable (comportement préservé)."""

    def test_policy_strict_leve_toujours_sur_span_faible(self, tmp_path):
        v = Vault(
            key=KEY,
            scope="s",
            registry_path=str(tmp_path / "r.db"),
            policy="strict",
        )
        try:
            # « Paris » isolé sans indice d'adresse = span faible (0.5).
            with pytest.raises(UnresolvedSpanError):
                v.mask("Je vais à Paris.")
        finally:
            v.close()

    def test_policy_strict_masque_les_spans_forts(self, tmp_path):
        v = Vault(
            key=KEY,
            scope="s",
            registry_path=str(tmp_path / "r.db"),
            policy="strict",
        )
        try:
            m = v.mask("M. Jean Dupont")
            assert m.entities, "les spans déclenchés doivent être masqués en strict"
            assert "Dupont" not in m.text
        finally:
            v.close()

    def test_audit_conserve_les_weak_spans(self, tmp_path, detect_calls):
        journal = tmp_path / "audit.jsonl"
        v = Vault(
            key=KEY,
            scope="s",
            registry_path=str(tmp_path / "r.db"),
            audit=AuditLog(str(journal)),
        )
        try:
            v.mask("Je vais à Paris.")
            entry = json.loads(journal.read_text(encoding="utf-8").strip().splitlines()[-1])
            assert "weak_spans" in entry
            weak = entry["weak_spans"]
            assert isinstance(weak, list) and weak, (
                f"les métadonnées de spans faibles doivent être journalisées: {entry!r}"
            )
            for item in weak:
                assert set(item) <= {"entity_type", "confidence", "rule_id"}
            assert "Paris" not in json.dumps(weak, ensure_ascii=False)
        finally:
            v.close()

    def test_audit_detecte_pour_alimenter_weak_spans(self, tmp_path, detect_calls):
        """Avec audit, la détection préalable est nécessaire (weak_spans)."""
        v = Vault(
            key=KEY,
            scope="s",
            registry_path=str(tmp_path / "r.db"),
            audit=AuditLog(str(tmp_path / "audit.jsonl")),
        )
        try:
            v.mask("Je vais à Paris.")
            assert detect_calls["n"] >= 1, "avec audit, detect() doit fournir les weak_spans"
        finally:
            v.close()
