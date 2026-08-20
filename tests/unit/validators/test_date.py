"""Tests du validateur date (phase 06).

Logique testée: validation calendaire d'une date au format JJ/MM/AAAA via
`datetime.date`. Cas limites couverts: 29 février bissextile vs non-bissextile,
mois 13 invalide, jour 31 sur mois de 30 jours, année/limites.
"""

from __future__ import annotations

from anonyfy.detect.validators.date import detect, validate


class TestDateValidate:
    def test_valide_plan(self):
        assert validate("15/03/1993") is True

    def test_invalide_plan_31_fevrier(self):
        assert validate("31/02/2021") is False

    def test_valide_29_fevrier_bissextile(self):
        assert validate("29/02/2020") is True

    def test_invalide_29_fevrier_non_bissextile(self):
        assert validate("29/02/2021") is False

    def test_invalide_mois_13(self):
        assert validate("01/13/2021") is False

    def test_invalide_mois_zero(self):
        assert validate("01/00/2021") is False

    def test_invalide_jour_zero(self):
        assert validate("00/01/2021") is False

    def test_invalide_jour_31_avril(self):
        # Avril a 30 jours.
        assert validate("31/04/2021") is False

    def test_valide_31_decembre(self):
        assert validate("31/12/2021") is True

    def test_invalide_jour_32(self):
        assert validate("32/01/2021") is False

    def test_invalide_format_iso(self):
        # Le format attendu est JJ/MM/AAAA, pas ISO.
        assert validate("1993-03-15") is False

    def test_invalide_separateur_point(self):
        assert validate("15.03.1993") is False

    def test_invalide_annee_deux_chiffres(self):
        assert validate("15/03/93") is False

    def test_invalide_chaine_vide(self):
        assert validate("") is False

    def test_invalide_texte(self):
        assert validate("pas une date") is False


class TestDateDetect:
    def test_detecte_date_dans_texte(self):
        spans = detect("né le 15/03/1993 à Paris")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "15/03/1993"
        assert s.type.value == "DATE"
        assert s.start == 6
        assert s.end == 16
        assert s.confidence < 1.0

    def test_aucun_span_si_date_inexistante(self):
        assert detect("date 31/02/2021 ici") == []

    def test_detecte_plusieurs_dates(self):
        spans = detect("du 01/01/2020 au 31/12/2020")
        assert len(spans) == 2

    def test_pas_de_match_partiel_dans_iso(self):
        # 1993-03-15 ne doit pas produire un span sur 03/15.
        assert detect("1993-03-15") == []
