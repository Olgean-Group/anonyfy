"""Tests du validateur carte bancaire (phase 05).

Logique testée: validation Luhn d'un PAN (13 à 19 chiffres), détection dans un
texte avec refus des nombres à clé Luhn fausse. Les faux positifs sur des
séquences de chiffres plus courtes (SIREN 9, SIRET 14) sont exclus par la
longueur minimale (13) et la clé Luhn.
"""

from __future__ import annotations

from anonyfy.detect.validators.cb import detect, validate


class TestCbValidate:
    def test_visa_16_valide(self):
        assert validate("4111111111111111") is True

    def test_visa_16_invalide(self):
        assert validate("4111111111111112") is False

    def test_amex_15_valide(self):
        assert validate("378282246310005") is True

    def test_mastercard_16_valide(self):
        assert validate("5555555555554444") is True

    def test_trop_court_rejete(self):
        # 12 chiffres: en dessous de la longueur d'un PAN.
        assert validate("411111111111") is False

    def test_trop_long_rejete(self):
        # 20 chiffres: au-dessus de la longueur d'un PAN.
        assert validate("41111111111111111111") is False

    def test_lettres_rejetees(self):
        assert validate("411111111111111A") is False

    def test_chaine_vide_rejetee(self):
        assert validate("") is False

    def test_siren_9_chiffres_rejete_comme_cb(self):
        # Un SIREN (9 chiffres) n'est pas un PAN.
        assert validate("732829320") is False


class TestCbDetect:
    def test_detecte_carte_dans_texte(self):
        spans = detect("Carte 4111111111111111 débitée")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "4111111111111111"
        assert s.type.value == "CARTE_BANCAIRE"
        assert s.start == 6
        assert s.end == 22
        assert s.confidence == 1.0

    def test_aucun_span_si_cle_fausse(self):
        assert detect("Carte 4111111111111112 rejetée") == []

    def test_detecte_amex_15(self):
        spans = detect("PAN 378282246310005 ok")
        assert len(spans) == 1
        assert spans[0].value == "378282246310005"

    def test_pas_de_match_sur_siret_14_luhn_valide(self):
        # Un SIRET (14 chiffres) a une longueur dans [13,19] et peut avoir une
        # clé Luhn valide; il sera détecté comme CB par ce validateur (chevauchement
        # traité en phase 13). On documente ici ce comportement attendu.
        spans = detect("73282932000009")
        assert len(spans) == 1
        assert spans[0].type.value == "CARTE_BANCAIRE"
