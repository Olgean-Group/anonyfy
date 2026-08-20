"""Détection des communes et voies par gazetteer (phase 13).

Étend la détection phase 12 (prenoms/noms) aux communes (``load_communes``) et
voies (``load_voies``). Match mot-à-mot/phrase contre les gazetteers, insensible
à la casse, avec offsets et confiance. Mécanisme minimal (pas de fuzzy/stemming).

Référence: PLAN.md phase 13, décision D20 (pré-autorisation détection communes/voies).
"""

from __future__ import annotations

from anonyfy.detect.context.places import detect
from anonyfy.types import EntityType


class TestDetectCommunes:
    def test_commune_paris_detectee(self) -> None:
        spans = detect("demeurant 75001 Paris")
        communes = [s for s in spans if s.type == EntityType.COMMUNE]
        assert len(communes) == 1
        c = communes[0]
        assert c.value.lower() == "paris"
        assert "Paris" in "demeurant 75001 Paris"[c.start : c.end]
        assert 0.0 < c.confidence <= 1.0

    def test_commune_avec_departement_attribut(self) -> None:
        spans = detect("à Lyon")
        communes = [s for s in spans if s.type == EntityType.COMMUNE]
        assert len(communes) == 1
        assert communes[0].value.lower() == "lyon"

    def test_commune_multi_mot_arboys(self) -> None:
        # "Arboys en Bugey" est une commune multi-mot réelle du gazetteer.
        spans = detect("à Arboys en Bugey")
        communes = [s for s in spans if s.type == EntityType.COMMUNE]
        assert len(communes) == 1
        assert communes[0].value.lower() == "arboys en bugey"

    def test_texte_sans_commune_renvoie_vide(self) -> None:
        spans = detect("bonjour tout le monde 12345")
        assert [s for s in spans if s.type == EntityType.COMMUNE] == []

    def test_offsets_pointent_vers_le_texte(self) -> None:
        text = "habite Paris"
        spans = detect(text)
        for s in spans:
            if s.type == EntityType.COMMUNE:
                assert text[s.start : s.end].casefold() == s.value.casefold()


class TestDetectVoies:
    def test_voie_rue_de_la_paix_detectee(self) -> None:
        spans = detect("12 rue de la Paix 75001")
        voies = [s for s in spans if s.type == EntityType.VOIE]
        assert len(voies) == 1
        v = voies[0]
        assert v.value.lower() == "rue de la paix"
        assert "rue de la Paix" in "12 rue de la Paix 75001"[v.start : v.end]

    def test_voie_offset_correct(self) -> None:
        text = "demeure 12 rue de la Paix à Paris"
        spans = detect(text)
        for s in spans:
            if s.type == EntityType.VOIE:
                assert text[s.start : s.end].casefold() == s.value.casefold()

    def test_voie_et_commune_dans_meme_texte(self) -> None:
        spans = detect("12 rue de la Paix 75001 Paris")
        types = {s.type for s in spans}
        assert EntityType.VOIE in types
        assert EntityType.COMMUNE in types

    def test_confidence_dans_plage(self) -> None:
        spans = detect("12 rue de la Paix Paris")
        for s in spans:
            assert 0.0 < s.confidence <= 1.0


class TestArbitrageNaturel:
    def test_pas_de_span_suprenant_hors_gazetteer(self) -> None:
        # "rue" seul n'est pas une voie (trop court / non dans le gazetteer comme
        # entrée standalone). On ne doit pas émettre de span VOIE pour "rue".
        spans = detect("il est dans la rue")
        voies = [s for s in spans if s.type == EntityType.VOIE]
        # Soit aucun span voie, soit le span ne couvre pas juste "rue".
        for v in voies:
            assert v.value.lower() != "rue"
