"""Tests de l'algorithme de Luhn (phase 05).

Logique testée: somme de contrôle de Luhn pour SIREN, SIRET, carte bancaire.
Vérifie des identifiants dont la clé est valide ET invalide, plus cas limites
(chaîne vide, lettres, longueur minimale).
"""

from __future__ import annotations

import pytest

from anonyfy.detect.validators.luhn import is_valid_luhn, luhn_checksum


class TestLuhnChecksum:
    def test_siren_valide_plan(self):
        # SIREN 732829320: clé Luhn valide (critère d'acceptation PLAN phase 05).
        assert luhn_checksum("732829320") == 0

    def test_siren_invalide_plan(self):
        # 732829321: clé incorrecte, la somme n'est pas nulle.
        assert luhn_checksum("732829321") != 0

    def test_carte_bancaire_visa_test(self):
        # 4111111111111111: carte de test Visa, Luhn valide.
        assert luhn_checksum("4111111111111111") == 0

    def test_carte_bancaire_invalide(self):
        assert luhn_checksum("4111111111111112") != 0

    def test_amex_15_chiffres(self):
        # 378282246310005: carte de test Amex (15 chiffres), Luhn valide.
        assert luhn_checksum("378282246310005") == 0


class TestIsValidLuhn:
    def test_siren_valide(self):
        assert is_valid_luhn("732829320") is True

    def test_siren_invalide(self):
        assert is_valid_luhn("732829321") is False

    def test_siret_valide(self):
        # SIRET dérivé du SIREN 732829320 + NIC 00009, Luhn valide sur 14 chiffres.
        assert is_valid_luhn("73282932000009") is True

    def test_siret_invalide(self):
        # Même SIRET avec dernier chiffre changé: clé Luhn fausse.
        assert is_valid_luhn("73282932000000") is False

    def test_chaine_vide_invalide(self):
        # Une chaîne vide n'a pas de clé Luhn; rejetée sans erreur.
        assert is_valid_luhn("") is False

    def test_lettres_rejetees(self):
        # Luhn ne s'applique qu'à des chiffres; les lettres sont rejetées.
        assert is_valid_luhn("7328A9320") is False

    def test_espaces_rejetes(self):
        # Les espaces ne sont pas des chiffres: rejeté.
        assert is_valid_luhn("7328 29320") is False