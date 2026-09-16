"""Phase 52 — REV-MIN-1/7/8 : formalisation F3-type, flush public, chargement unique.

Trois constats MINEUR de la revue S8 (jalon 0.1.5) :

- REV-MIN-1 : l'invariant F3-type (« substitut de même type ») n'était pas
  formalisé dans ``invariants.py`` ; chaque test vérifiait son propre type
  attendu. Un vérificateur unique doit rendre une violation visible partout.
- REV-MIN-7 : ``Vault`` n'exposait pas de ``flush()`` public alors que
  ``ScopeRegistry`` en a un : un opérateur qui publie un masqué juste après
  ``mask()`` pouvait perdre le batch en cours (durabilité « au batch près »).
- REV-MIN-8 : ``_check_gazetteer_version`` rechargeait le registre en mémoire
  (boucle ``SELECT``) alors que ``_load_into_memory`` le fait juste après ;
  double chargement inutile.

Référence: ``.olgenius/REVUE-CODE.html`` (S8.2), BACKLOG REV-MIN-1/7/8.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anonyfy import Vault
from anonyfy.invariants import (
    InvariantViolation,
    SameTypeViolation,
    assert_substitute_same_type,
)
from anonyfy.surrogate.registry import ScopeRegistry
from anonyfy.types import EntityType, Span

_KEY = b"0" * 16


def _vault(tmp_path: Path, scope: str = "s") -> Vault:
    return Vault(key=_KEY, scope=scope, registry_path=str(tmp_path / "r.db"))


def _span(value: str, entity_type: EntityType, rule_id: str, confidence: float = 1.0) -> Span:
    return Span(0, len(value), entity_type, value, rule_id, confidence)


class TestAssertSubstituteSameType:
    """REV-MIN-1 : vérificateur pur de l'invariant F3-type."""

    def test_accepts_matching_type_and_rule(self):
        span = _span("Paris", EntityType.COMMUNE, "mask-commune")
        assert_substitute_same_type(span, EntityType.COMMUNE)

    def test_rejects_span_typed_patronyme_for_a_commune_expectation(self):
        span = _span("Paris", EntityType.PATRONYME, "mask-patronyme")
        with pytest.raises(SameTypeViolation):
            assert_substitute_same_type(span, EntityType.COMMUNE)

    def test_rejects_rule_id_not_matching_declared_type(self):
        """Un span typé COMMUNE mais substitué par une règle d'un autre type
        (repli silencieux) doit lever."""
        span = _span("Paris", EntityType.COMMUNE, "mask-patronyme")
        with pytest.raises(SameTypeViolation):
            assert_substitute_same_type(span, EntityType.COMMUNE)

    def test_violation_is_an_invariant_violation(self):
        span = _span("Paris", EntityType.PATRONYME, "mask-patronyme")
        with pytest.raises(InvariantViolation):
            assert_substitute_same_type(span, EntityType.COMMUNE)

    def test_accepts_pre_detection_rule_ids_for_the_declared_type(self):
        """Les spans de détection (avant masquage) n'ont pas de règle ``mask-`` :
        seul le type est alors vérifié."""
        span = _span("Paris", EntityType.COMMUNE, "gazetteer-commune")
        assert_substitute_same_type(span, EntityType.COMMUNE)

    def test_rejects_expected_type_not_matching_declared_type(self):
        span = _span("Paris", EntityType.COMMUNE, "gazetteer-commune")
        with pytest.raises(SameTypeViolation):
            assert_substitute_same_type(span, EntityType.VOIE)


class TestF3TypeEndToEnd:
    """Le vérificateur appliqué au masquage réel : chaque type est cohérent."""

    @pytest.mark.parametrize(
        "text,token,expected",
        [
            ("demeurant à Paris", "Paris", EntityType.COMMUNE),
            ("domicilié à Lyon", "Lyon", EntityType.COMMUNE),
            ("12 rue de la Paix", "rue de la Paix", EntityType.VOIE),
            ("M. Boisseau", "Boisseau", EntityType.PATRONYME),
        ],
    )
    def test_masked_type_is_coherent(self, tmp_path, text, token, expected):
        v = _vault(tmp_path)
        try:
            m = v.mask(text)
            offset = text.index(token)
            span = next(
                (s for s in m.entities if s.start == offset or s.start <= offset < s.end), None
            )
            assert span is not None, f"aucun span pour {token!r} dans {text!r}: {m.entities!r}"
            assert_substitute_same_type(span, expected)
        finally:
            v.close()


class TestFlushPublic:
    """REV-MIN-7 : ``Vault.flush()`` expose le commit du batch en cours."""

    def test_vault_exposes_flush(self, tmp_path):
        v = _vault(tmp_path)
        try:
            assert hasattr(v, "flush")
        finally:
            v.close()

    def test_flush_persists_reservations_across_reopen(self, tmp_path):
        """Après ``flush()``, un second Vault sur le même registre voit les
        substituts déjà attribués (durabilité au batch près)."""
        registry_path = tmp_path / "r.db"
        v1 = Vault(key=_KEY, scope="s", registry_path=str(registry_path))
        try:
            first = v1.mask("SIRET 73282932000033").text
            v1.flush()
        finally:
            v1.close()

        v2 = Vault(key=_KEY, scope="s", registry_path=str(registry_path))
        try:
            again = v2.mask("SIRET 73282932000033").text
            assert again == first, "le flush n'a pas persisté la réservation"
        finally:
            v2.close()

    def test_flush_is_idempotent(self, tmp_path):
        v = _vault(tmp_path)
        try:
            v.mask("SIRET 73282932000033")
            v.flush()
            v.flush()
        finally:
            v.close()


class TestSingleRegistryLoad:
    """REV-MIN-8 : le registre n'est chargé qu'une fois à l'ouverture."""

    def test_check_gazetteer_version_does_not_reload_entries(self, tmp_path, monkeypatch):
        registry_path = tmp_path / "r.db"
        seed = ScopeRegistry(key=_KEY, scope="s", registry_path=str(registry_path))
        seed.register_fpe("SIRET", "73282932000033", surrogate="73282932000034")
        seed.close()

        calls = {"load": 0}
        original = ScopeRegistry._load_into_memory

        def counting(self):
            calls["load"] += 1
            return original(self)

        monkeypatch.setattr(ScopeRegistry, "_load_into_memory", counting)
        registry = ScopeRegistry(key=_KEY, scope="s", registry_path=str(registry_path))
        try:
            assert calls["load"] == 1, (
                f"le registre a été chargé {calls['load']} fois à l'ouverture"
            )
        finally:
            registry.close()
