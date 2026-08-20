"""Tests de l'arbitrage des chevauchements structurés (phase 08, PRD F2).

Priorité de résolution: spécificité (confidence) > longueur > priorité déclarée.
L'arbitrage ne couvre que les types structurés (D2: NIR, SIREN, SIRET, IBAN, TVA,
CB, téléphone). Les chevauchements non structurés (patronyme, plaque, etc.) sont
hors périmètre (phase 13).

Référence: PLAN.md phase 08, PRD F2.
"""

from __future__ import annotations

from anonyfy.resolve.arbitrage import resolve_overlaps
from anonyfy.types import EntityType, Span


def _span(start: int, end: int, t: EntityType, value: str, conf: float = 1.0) -> Span:
    return Span(start=start, end=end, type=t, value=value, rule_id="test", confidence=conf)


class TestResolveOverlaps:
    def test_aucun_chevauchement_renvoie_tout(self) -> None:
        spans = [
            _span(0, 9, EntityType.SIREN, "123456782"),
            _span(20, 35, EntityType.IBAN, "FR7612345678901234567890189"),
        ]
        resolved = resolve_overlaps(spans)
        assert len(resolved) == 2

    def test_siret_contient_siren_garde_siret(self) -> None:
        """Un SIRET (14 chiffres) dont les 9 premiers forment un SIREN valide:
        l'arbitrage garde le SIRET (plus long, même confiance)."""
        spans = [
            _span(0, 14, EntityType.SIRET, "73282932000033"),
            _span(0, 9, EntityType.SIREN, "732829320"),
        ]
        resolved = resolve_overlaps(spans)
        types = {s.type for s in resolved}
        assert EntityType.SIRET in types
        assert EntityType.SIREN not in types

    def test_specificite_bat_longueur(self) -> None:
        """Confidence plus élevée gagne même si l'autre span est plus long."""
        # SIRET confiance 1.0 (9 chiffres) vs téléphone confiance 0.9 (10 chiffres)
        # Le téléphone est plus long mais moins spécifique.
        spans = [
            _span(0, 9, EntityType.SIREN, "123456782", conf=1.0),
            _span(0, 10, EntityType.TELEPHONE, "0123456789", conf=0.9),
        ]
        resolved = resolve_overlaps(spans)
        types = {s.type for s in resolved}
        assert EntityType.SIREN in types
        assert EntityType.TELEPHONE not in types

    def test_longueur_bat_priorite_declaree(self) -> None:
        """À confidence égale, le span plus long gagne."""
        spans = [
            _span(0, 14, EntityType.SIRET, "73282932000033"),
            _span(0, 9, EntityType.SIREN, "732829320"),
        ]
        resolved = resolve_overlaps(spans)
        # SIRET (14) plus long que SIREN (9), même confiance 1.0 -> SIRET gagne
        assert all(s.type != EntityType.SIREN for s in resolved)

    def test_priorite_declaree_bat_egalite(self) -> None:
        """À confidence et longueur égales, la priorité déclarée tranche.
        SIRET vs CB (tous deux 14 chiffres Luhn-valides, confiance 1.0):
        SIRET est plus spécifique (format strict 14 chiffres avec structure SIREN)
        que CB (13-19 chiffres), donc SIRET gagne."""
        value = "73282932000033"  # 14 chiffres, Luhn-valide
        spans = [
            _span(0, 14, EntityType.SIRET, value),
            _span(0, 14, EntityType.CARTE_BANCAIRE, value),
        ]
        resolved = resolve_overlaps(spans)
        types = {s.type for s in resolved}
        assert EntityType.SIRET in types
        assert EntityType.CARTE_BANCAIRE not in types

    def test_chevauchement_partiel_garde_plus_specifique(self) -> None:
        """Chevauchement partiel: le span plus spécifique (confiance) garde
        sa place, l'autre est tronqué/exclu."""
        spans = [
            _span(0, 14, EntityType.SIRET, "73282932000033", conf=1.0),
            _span(5, 19, EntityType.TELEPHONE, "0123456789", conf=0.9),
        ]
        resolved = resolve_overlaps(spans)
        # SIRET confiance 1.0 > téléphone 0.9, SIRET gardé
        assert any(s.type == EntityType.SIRET for s in resolved)
        assert all(s.type != EntityType.TELEPHONE for s in resolved)

    def test_liste_vide_renvoie_vide(self) -> None:
        assert resolve_overlaps([]) == []

    def test_conserve_ordre_par_position(self) -> None:
        """Les spans résolus sont renvoyés triés par position de début."""
        spans = [
            _span(20, 35, EntityType.IBAN, "FR7612345678901234567890189"),
            _span(0, 9, EntityType.SIREN, "123456782"),
        ]
        resolved = resolve_overlaps(spans)
        assert resolved[0].start < resolved[1].start

    def test_spans_non_chevauchants_tous_conserves(self) -> None:
        spans = [
            _span(0, 9, EntityType.SIREN, "123456782"),
            _span(10, 25, EntityType.IBAN, "FR7612345678901234567890189"),
            _span(30, 45, EntityType.NIR, "275032917028004"),
        ]
        resolved = resolve_overlaps(spans)
        assert len(resolved) == 3