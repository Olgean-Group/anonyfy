"""Tests du validateur TVA intracommunautaire FR (phase 05).

Logique testée: validation de la clé TVA FR = (12 + 3 * (SIREN mod 97)) mod 97
sur le format "FR" + 2 chiffres de clé + 9 chiffres de SIREN. Couvre valides,
invalides (clé fausse), et détection dans un texte.

Référence: formule DGFiP / VIES; exemple SIREN 404833048 -> clé 83.
"""

from __future__ import annotations

from anonyfy.detect.validators.tva import detect, validate


class TestTvaValidate:
    def test_valide_exemple_dgfip(self):
        # SIREN 404833048 -> clé 83.
        assert validate("FR83404833048") is True

    def test_invalide_cle_fausse(self):
        # Même SIREN, clé 84 au lieu de 83.
        assert validate("FR84404833048") is False

    def test_valide_siren_plan(self):
        # SIREN 732829320 -> clé 44.
        assert validate("FR44732829320") is True

    def test_invalide_cle_zero(self):
        assert validate("FR00404833048") is False

    def test_trop_court_rejete(self):
        assert validate("FR8340483304") is False

    def test_trop_long_rejete(self):
        assert validate("FR834048330480") is False

    def test_minuscule_rejetee(self):
        # Le format exige "FR" en majuscules.
        assert validate("fr83404833048") is False

    def test_autre_pays_rejete(self):
        assert validate("DE83404833048") is False

    def test_chaine_vide_rejetee(self):
        assert validate("") is False


class TestTvaDetect:
    def test_detecte_tva_dans_texte(self):
        spans = detect("TVA FR83404833048 du fournisseur")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "FR83404833048"
        assert s.type.value == "TVA"
        assert s.start == 4
        assert s.end == 17
        assert s.confidence == 1.0

    def test_aucun_span_si_cle_fausse(self):
        assert detect("TVA FR84404833048 invalide") == []

    def test_pas_de_match_sur_siren_seul(self):
        # "FR732829320" n'est pas une TVA (10 chiffres au lieu de 11 après FR).
        assert detect("FR732829320") == []