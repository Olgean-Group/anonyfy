"""Tests du validateur IBAN FR (phase 05).

Logique testée: validation mod 97 d'un IBAN français (27 caractères, FR + clé +
BBAN), détection dans un texte, refus des IBAN à clé fausse et des chaînes
mal formées (lettres dans le BBAN, mauvaise longueur, autre pays).
"""

from __future__ import annotations

from anonyfy.detect.validators.iban import detect, validate


class TestIbanValidate:
    def test_valide_plan(self):
        assert validate("FR7630006000011234567890189") is True

    def test_invalide_plan(self):
        assert validate("FR7630006000011234567890180") is False

    def test_trop_court_rejete(self):
        assert validate("FR763000600001123456789018") is False

    def test_trop_long_rejete(self):
        assert validate("FR76300060000112345678901890") is False

    def test_autre_pays_rejete(self):
        # Le validateur est ciblé FR; un IBAN d'un autre pays n'est pas accepté.
        assert validate("DE89370400440532013000") is False

    def test_lettres_dans_bban_rejetees(self):
        # Un BBAN ne contient que des chiffres en France.
        assert validate("FR7630006000011234567890A89") is False

    def test_chaine_vide_rejetee(self):
        assert validate("") is False


class TestIbanDetect:
    def test_detecte_iban_dans_texte(self):
        spans = detect("Virement IBAN FR7630006000011234567890189 clôturé")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "FR7630006000011234567890189"
        assert s.type.value == "IBAN"
        assert s.start == 14
        assert s.end == 41
        assert s.confidence == 1.0
        assert s.rule_id == "iban-mod97"

    def test_aucun_span_si_cle_fausse(self):
        assert detect("IBAN FR7630006000011234567890180 faux") == []

    def test_pas_de_match_dans_texte_sans_iban(self):
        assert detect("Aucun iban FR76 mentionné") == []