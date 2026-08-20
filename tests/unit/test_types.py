"""Tests du socle de types de la phase 04.

Couvre: EntityType, Span, Entity, Rule, MaskedText, AuditEntry.
Logique testée: invariants de construction des dataclasses frozen, validation
des champs (offsets, confiance, type d'entité), immuabilité.
"""

from __future__ import annotations

import dataclasses

import pytest

from anonyfy.types import AuditEntry, Entity, EntityType, MaskedText, Rule, Span


class TestEntityType:
    def test_membres_couvrent_types_prd(self):
        # Les types d'entité attendus par le PRD §7 doivent tous exister.
        attendus = {
            "NIR",
            "SIREN",
            "SIRET",
            "IBAN",
            "TVA",
            "CARTE_BANCAIRE",
            "TELEPHONE",
            "PLAQUE_SIV",
            "REFERENCE_DOSSIER",
            "EMAIL",
            "DATE",
            "PATRONYME",
            "PRENOM",
            "COMMUNE",
            "VOIE",
        }
        noms = {e.name for e in EntityType}
        manquants = attendus - noms
        assert not manquants, f"EntityType manque: {manquants}"

    def test_membres_uniques(self):
        noms = [e.name for e in EntityType]
        assert len(noms) == len(set(noms))


class TestSpan:
    def test_construction_valide(self):
        s = Span(start=0, end=3, type="SIRET", value="123", rule_id="r", confidence=1.0)
        assert s.start == 0
        assert s.end == 3
        assert s.type is EntityType.SIRET
        assert s.value == "123"
        assert s.rule_id == "r"
        assert s.confidence == 1.0

    def test_type_depuis_enum_accepte(self):
        s = Span(start=0, end=2, type=EntityType.NIR, value="12", rule_id="r", confidence=0.5)
        assert s.type is EntityType.NIR

    def test_type_inconnu_leve(self):
        # Un type d'entité inconnu doit echouer a la construction.
        with pytest.raises(ValueError):
            Span(start=0, end=2, type="INCONNU", value="12", rule_id="r", confidence=1.0)

    def test_start_negatif_leve(self):
        with pytest.raises(ValueError):
            Span(start=-1, end=2, type="SIRET", value="12", rule_id="r", confidence=1.0)

    def test_end_avant_start_leve(self):
        with pytest.raises(ValueError):
            Span(start=5, end=3, type="SIRET", value="12", rule_id="r", confidence=1.0)

    def test_end_egal_start_leve(self):
        # Un span vide n'est pas une entite.
        with pytest.raises(ValueError):
            Span(start=3, end=3, type="SIRET", value="", rule_id="r", confidence=1.0)

    def test_confidence_hors_borne_leve(self):
        with pytest.raises(ValueError):
            Span(start=0, end=2, type="SIRET", value="12", rule_id="r", confidence=1.5)
        with pytest.raises(ValueError):
            Span(start=0, end=2, type="SIRET", value="12", rule_id="r", confidence=-0.1)

    def test_confidence_bornes_inclusives(self):
        Span(start=0, end=2, type="SIRET", value="12", rule_id="r", confidence=0.0)
        Span(start=0, end=2, type="SIRET", value="12", rule_id="r", confidence=1.0)

    def test_frozen_immuable(self):
        s = Span(start=0, end=2, type="SIRET", value="12", rule_id="r", confidence=1.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.value = "autre"  # type: ignore[misc]


class TestMaskedText:
    def test_construction_text_et_entities(self):
        s = Span(start=0, end=3, type="SIRET", value="123", rule_id="r", confidence=1.0)
        m = MaskedText(text="ABC", entities=(s,))
        assert m.text == "ABC"
        assert m.entities == (s,)

    def test_entities_defaut_tuple_vide(self):
        m = MaskedText(text="rien")
        assert m.entities == ()

    def test_frozen_immuable(self):
        m = MaskedText(text="ABC")
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.text = "XYZ"  # type: ignore[misc]


class TestEntity:
    def test_construction_span_et_substitut(self):
        s = Span(start=0, end=3, type="SIRET", value="123", rule_id="r", confidence=1.0)
        e = Entity(span=s, substitute="456")
        assert e.span is s
        assert e.substitute == "456"

    def test_frozen_immuable(self):
        s = Span(start=0, end=3, type="SIRET", value="123", rule_id="r", confidence=1.0)
        e = Entity(span=s, substitute="456")
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.substitute = "autre"  # type: ignore[misc]


class TestRule:
    def test_construction_id_et_type(self):
        r = Rule(id="siret-luhn", type="SIRET")
        assert r.id == "siret-luhn"
        assert r.type is EntityType.SIRET

    def test_type_inconnu_leve(self):
        with pytest.raises(ValueError):
            Rule(id="x", type="INCONNU")


class TestAuditEntry:
    def test_construction_champs_meta(self):
        e = AuditEntry(
            timestamp="2026-08-20T10:00:00Z",
            scope="dossier-1234",
            rule_id="siret-luhn",
            digest="abcd",
            span_count=1,
            entity_type="SIRET",
        )
        assert e.scope == "dossier-1234"
        assert e.span_count == 1
        assert e.entity_type is EntityType.SIRET

    def test_aucun_champ_texte_clair(self):
        # Invariant 1 (audit): aucune valeur claire n'est stockee dans une entree.
        # Le AuditEntry ne doit pas porter de champ libre texte claire/substitut.
        champs = {f.name for f in dataclasses.fields(AuditEntry)}
        interdits = {"text", "clear", "plaintext", "value", "substitute", "original"}
        assert not (champs & interdits), f"champs interdits: {champs & interdits}"

    def test_frozen_immuable(self):
        e = AuditEntry(
            timestamp="t",
            scope="s",
            rule_id="r",
            digest="d",
            span_count=1,
            entity_type="SIRET",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.scope = "autre"  # type: ignore[misc]
