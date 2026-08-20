"""Arbitrage complet: chevauchements gazetteer+structuré et priorité gazetteer.

Phase 13 étend l'arbitrage phase 08 (structurés) aux cas mixtes:
  - gazetteer (patronyme/prenom/commune/voie) vs structuré (SIRET/date/email/...);
  - gazetteer vs gazetteer (voie vs commune, commune vs patronyme).

Règle inchangée: spécificité (confidence) > longueur > priorité déclarée. Une
priorité déclarée différenciée est introduite pour les types gazetteer afin de
trancher les égalités (voie > commune > patronyme > prenom): une voie est plus
spécifique qu'une commune, elle-même plus spécifique qu'un patronyme isolé.

Référence: PLAN.md phase 13, PRD F2.
"""

from __future__ import annotations

from anonyfy.resolve.arbitrage import resolve_overlaps
from anonyfy.types import EntityType, Span


def _span(start: int, end: int, t: EntityType, value: str, conf: float = 0.9) -> Span:
    return Span(start=start, end=end, type=t, value=value, rule_id="test", confidence=conf)


class TestGazetteerVsStructure:
    def test_email_absorbe_prenom_et_patronyme_inclus(self) -> None:
        """Un email ``jean.dupont@exemple.fr`` contient les candidats gazetteer
        « jean » (prenom) et « dupont » (patronyme). L'arbitrage garde l'email
        (plus long, même confiance) et exclut les candidats gazetteer inclus
        (pas de double masquage de la local-part)."""
        spans = [
            _span(0, 24, EntityType.EMAIL, "jean.dupont@exemple.fr"),
            _span(0, 4, EntityType.PRENOM, "jean"),
            _span(9, 15, EntityType.PATRONYME, "patronyme"),
        ]
        resolved = resolve_overlaps(spans)
        types = {s.type for s in resolved}
        assert EntityType.EMAIL in types
        assert EntityType.PRENOM not in types
        assert EntityType.PATRONYME not in types

    def test_siret_bat_patronyme_confiance_superieure(self) -> None:
        """Un SIRET (confiance 1.0) gagne contre un patronyme (confiance 0.9)
        chevauchant: la spécificité (confidence) l'emporte sur la longueur."""
        spans = [
            _span(0, 14, EntityType.SIRET, "73282932000033", conf=1.0),
            _span(0, 6, EntityType.PATRONYME, "Martin", conf=0.9),
        ]
        resolved = resolve_overlaps(spans)
        assert any(s.type == EntityType.SIRET for s in resolved)
        assert all(s.type != EntityType.PATRONYME for s in resolved)


class TestGazetteerVsGazetteer:
    def test_voie_plus_longue_que_patronyme_inclus_gagne(self) -> None:
        """« rue de la Paix » (voie, 14 chars) contient « Paix » (patronyme). La
        voie plus longue gagne (même confiance)."""
        spans = [
            _span(0, 14, EntityType.VOIE, "rue de la Paix"),
            _span(10, 14, EntityType.PATRONYME, "Paix"),
        ]
        resolved = resolve_overlaps(spans)
        assert any(s.type == EntityType.VOIE for s in resolved)
        assert all(s.type != EntityType.PATRONYME for s in resolved)

    def test_voie_bat_commune_a_egalite(self) -> None:
        """À confiance et longueur égales, une voie est plus spécifique qu'une
        commune (priorité déclarée VOIE > COMMUNE). Un homonyme voie/commune
        chevauchant: la voie gagne."""
        spans = [
            _span(0, 6, EntityType.COMMUNE, "Abbaye"),
            _span(0, 6, EntityType.VOIE, "Abbaye"),
        ]
        resolved = resolve_overlaps(spans)
        types = {s.type for s in resolved}
        assert EntityType.VOIE in types
        assert EntityType.COMMUNE not in types

    def test_commune_bat_patronyme_a_egalite(self) -> None:
        """À confiance et longueur égales, une commune est plus spécifique qu'un
        patronyme (priorité COMMUNE > PATRONYME)."""
        spans = [
            _span(0, 5, EntityType.PATRONYME, "Paris"),
            _span(0, 5, EntityType.COMMUNE, "Paris"),
        ]
        resolved = resolve_overlaps(spans)
        types = {s.type for s in resolved}
        assert EntityType.COMMUNE in types
        assert EntityType.PATRONYME not in types


class TestNonChevauchement:
    def test_gazetteer_et_structure_non_chevauchants_tous_conserves(self) -> None:
        spans = [
            _span(0, 4, EntityType.PRENOM, "Jean"),
            _span(5, 11, EntityType.PATRONYME, "Dupont"),
            _span(20, 34, EntityType.SIRET, "73282932000033", conf=1.0),
        ]
        resolved = resolve_overlaps(spans)
        assert len(resolved) == 3
