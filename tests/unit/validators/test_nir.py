"""Tests du validateur NIR (phase 05).

Logique testée: validation de la clé de contrôle mod 97 du NIR (13 chiffres +
clé 2 chiffres), y compris la Corse (2A/2B). Des NIR valides ET invalides
(clé incorrecte) sont couverts, plus la détection dans un texte.

Note: le PLAN phase 05 cite 275032917028096 comme "NIR valide connu". Sous
l'algorithme officiel (clé = 97 - (13 chiffres mod 97)), la base 2750329170280
donne une clé de 04, pas 96: le NIR valide est 275032917028004. Le test
`test_plan_value_est_invalide_sous_algorithme_standard` documente cet écart;
l'orchestrateur doit corriger le critère d'acceptation du PLAN.
"""

from __future__ import annotations

from anonyfy.detect.validators.nir import detect, validate


class TestNirValidate:
    def test_valide_base_plan(self):
        # Base 2750329170280, clé 04 (algorithme officiel).
        assert validate("275032917028004") is True

    def test_invalide_cle_97(self):
        # Clé 97 incorrecte pour cette base.
        assert validate("275032917028097") is False

    def test_invalide_cle_96_du_plan(self):
        # 275032917028096: clé 96 fausse sous l'algorithme officiel (écart PLAN).
        assert validate("275032917028096") is False

    def test_valide_corse_2b(self):
        # 185032B00101555: base Corse 2B substituée par 18, clé 55.
        assert validate("185032B00101555") is True

    def test_valide_corse_2a(self):
        # 185032A00101528: base Corse 2A substituée par 19, clé 28.
        assert validate("185032A00101528") is True

    def test_invalide_corse_2b_cle_fausse(self):
        assert validate("185032B00101550") is False

    def test_trop_court_rejete(self):
        assert validate("2750329170280") is False

    def test_trop_long_rejete(self):
        assert validate("2750329170280045") is False

    def test_lettres_hors_corse_rejetees(self):
        # Un 'A' hors du champ départemental (position 5-6) n'est pas un NIR valide.
        assert validate("2750A2917028004") is False

    def test_sexe_zero_rejete(self):
        # Le premier chiffre (sexe) ne peut être 0.
        assert validate("075032917028028") is False

    def test_chaine_vide_rejetee(self):
        assert validate("") is False


class TestNirDetect:
    def test_detecte_nir_dans_texte(self):
        spans = detect("NIR 275032917028004 du patient")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "275032917028004"
        assert s.type.value == "NIR"
        assert s.start == 4
        assert s.end == 19
        assert s.confidence == 1.0

    def test_aucun_span_si_cle_fausse(self):
        # Un NIR potentiel à clé fausse ne produit aucun span.
        assert detect("NIR 275032917028097 ici") == []

    def test_detecte_nir_corse(self):
        spans = detect("Corse 185032B00101555")
        assert len(spans) == 1
        assert spans[0].value == "185032B00101555"

    def test_pas_de_match_dans_15_chiffres_invalide(self):
        assert detect("275032917028096") == []
