"""Détection des dates textuelles françaises « JJ mois AAAA » (phase 13, D8).

Étend la détection phase 06 (JJ/MM/AAAA) au format textuel français avec le mois
en toutes lettres (janvier..décembre). Le validateur phase 06 reste intact; ce
module est un détecteur distinct réutilisable par le moteur.

Référence: PLAN.md phase 13 (D8, détection dates textuelles pré-autorisée D21).
"""

from __future__ import annotations

from anonyfy.detect.context.dates_text import detect
from anonyfy.types import EntityType


class TestDetectDatesText:
    def test_date_text_simple(self) -> None:
        spans = detect("né le 15 mars 1990")
        dates = [s for s in spans if s.type == EntityType.DATE]
        assert len(dates) == 1
        assert dates[0].value == "15 mars 1990"
        assert "15 mars 1990" in "né le 15 mars 1990"[dates[0].start : dates[0].end]

    def test_date_text_3_mai_1990(self) -> None:
        spans = detect("né le 3 mai 1990")
        dates = [s for s in spans if s.type == EntityType.DATE]
        assert len(dates) == 1
        assert dates[0].value == "3 mai 1990"

    def test_tous_les_mois(self) -> None:
        mois = [
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ]
        for m in mois:
            spans = detect(f"le 1 {m} 2000")
            dates = [s for s in spans if s.type == EntityType.DATE]
            assert len(dates) == 1, f"mois {m!r} non détecté"

    def test_date_text_jour_sur_deux_chiffres(self) -> None:
        spans = detect("le 31 décembre 1999")
        dates = [s for s in spans if s.type == EntityType.DATE]
        assert len(dates) == 1
        assert dates[0].value == "31 décembre 1999"

    def test_pas_de_date_invalisible(self) -> None:
        # 30 février n'existe pas: pas de span (validité calendaire).
        spans = detect("le 30 février 2023")
        assert [s for s in spans if s.type == EntityType.DATE] == []

    def test_annee_sur_4_chiffres_exigee(self) -> None:
        # "15 mars 90" (année 2 chiffres) n'est pas détecté (format AAAA requis).
        spans = detect("le 15 mars 90")
        assert [s for s in spans if s.type == EntityType.DATE] == []

    def test_confiance_dans_plage(self) -> None:
        spans = detect("né le 15 mars 1990")
        for s in spans:
            assert 0.0 < s.confidence <= 1.0

    def test_texte_sans_date_renvoie_vide(self) -> None:
        assert detect("bonjour tout le monde") == []

    def test_offset_correct(self) -> None:
        text = "né le 3 mai 1990 à Paris"
        spans = detect(text)
        for s in spans:
            if s.type == EntityType.DATE:
                assert text[s.start : s.end] == s.value
