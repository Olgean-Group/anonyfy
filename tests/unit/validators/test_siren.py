"""Tests des validateurs SIREN et SIRET (phase 05).

Logique testée: validation Luhn d'un SIREN (9 chiffres) et d'un SIRET
(14 chiffres); détection dans un texte avec refus des suites de chiffres dont
la clé Luhn est fausse (risque PLAN: "tout 14 chiffres = SIRET").
"""

from __future__ import annotations

from anonyfy.detect.validators.siren import detect, detect_siret, validate, validate_siret


class TestSirenValidate:
    def test_valide_plan(self):
        assert validate("732829320") is True

    def test_invalide_plan(self):
        assert validate("732829321") is False

    def test_valide_secondaire(self):
        assert validate("404833048") is True

    def test_trop_court_rejete(self):
        # 8 chiffres n'est pas un SIREN.
        assert validate("73282932") is False

    def test_trop_long_rejete(self):
        # 10 chiffres n'est pas un SIREN.
        assert validate("7328293200") is False

    def test_lettres_rejetees(self):
        assert validate("7328A9320") is False

    def test_chaine_vide_rejetee(self):
        assert validate("") is False


class TestSiretValidate:
    def test_valide(self):
        # SIRET 14 chiffres dérivé du SIREN 732829320, Luhn valide.
        assert validate_siret("73282932000009") is True

    def test_invalide_cle_luhn_fausse(self):
        # 14 chiffres mais clé Luhn fausse: doit échouer (mitigation risque PLAN).
        assert validate_siret("73282932000000") is False

    def test_trop_court_rejete(self):
        assert validate_siret("7328293200000") is False

    def test_trop_long_rejete(self):
        assert validate_siret("732829320000099") is False


class TestSirenDetect:
    def test_detecte_siren_dans_texte(self):
        spans = detect("SIREN 732829320 enregistré")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "732829320"
        assert s.type.value == "SIREN"
        assert s.start == 6
        assert s.end == 15
        assert s.confidence == 1.0

    def test_aucun_span_si_cle_fausse(self):
        # Un SIREN potentiel dont la clé Luhn est fausse ne produit aucun span.
        assert detect("SIREN 732829321 ici") == []

    def test_bornes_pas_de_match_partiel_dans_plus_long(self):
        # Un SIRET (14 chiffres) ne doit pas produire un span SIREN partiel.
        assert detect("73282932000009") == []


class TestSiretDetect:
    def test_detecte_siret_dans_texte(self):
        spans = detect_siret("SIRET 73282932000009 actif")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "73282932000009"
        assert s.type.value == "SIRET"
        assert s.start == 6
        assert s.end == 20

    def test_aucun_span_si_cle_luhn_fausse(self):
        # Risque PLAN: un 14 chiffres à clé fausse ne produit aucun span.
        assert detect_siret("Le siret 73282932000000 est faux") == []

    def test_pas_de_match_sur_9_chiffres(self):
        # Un SIREN (9 chiffres) n'est pas un SIRET.
        assert detect_siret("732829320 ici") == []