"""Tests du recalcul des clés de contrôle (phase 07).

Les substituts FPE doivent rester valides au format de l'original: on chiffre
le corps significatif et on **recale** la clé de contrôle (Luhn, mod 97 NIR,
mod 97 IBAN, clé TVA). Ce module valide chaque recomposition indépendamment de
FPE.

Référence: PLAN.md phase 07, ADR 0001 §2 (recalcul des clés).
"""

from __future__ import annotations

import pytest

from anonyfy.detect.validators import iban as iban_v
from anonyfy.detect.validators import mod97
from anonyfy.detect.validators import nir as nir_v
from anonyfy.detect.validators import siren as siren_v
from anonyfy.detect.validators import tva as tva_v
from anonyfy.detect.validators.luhn import is_valid_luhn
from anonyfy.surrogate import checksum


class TestLuhnCheckDigit:
    def test_recale_siren_valide(self):
        # SIREN 732829320: corps 73282932 + cle 0. Recalcul -> 0.
        assert checksum.luhn_check_digit("73282932") == 0

    def test_recale_siret_valide(self):
        # SIRET 73282932000033: corps 13 chiffres + cle 3.
        assert checksum.luhn_check_digit("7328293200003") == 3

    def test_recompose_siren_valide_luhn(self):
        body = "73282932"
        full = body + str(checksum.luhn_check_digit(body))
        assert siren_v.validate(full)

    def test_recompose_siret_valide_luhn(self):
        body = "7328293200003"
        full = body + str(checksum.luhn_check_digit(body))
        assert siren_v.validate_siret(full)

    @pytest.mark.parametrize("body", ["12345678", "9876543210123", "00000000"])
    def test_luhn_check_digit_rend_la_chaine_valide(self, body):
        c = checksum.luhn_check_digit(body)
        assert is_valid_luhn(body + str(c))

    def test_corps_non_numerique_leve_valueerror(self):
        with pytest.raises(ValueError):
            checksum.luhn_check_digit("12A456")

    def test_corps_vide_leve_valueerror(self):
        with pytest.raises(ValueError):
            checksum.luhn_check_digit("")


class TestNirKey:
    def test_cle_nir_reference_d16(self):
        # D16: NIR de reference 275032917028004 -> cle 04.
        assert checksum.nir_key("2750329170280") == "04"

    def test_recompose_nir_valide(self):
        base = "2750329170280"
        full = base + checksum.nir_key(base)
        assert nir_v.validate(full)

    def test_cle_nir_garde_deux_chiffres(self):
        key = checksum.nir_key("2750329170280")
        assert len(key) == 2
        assert key.isdigit()

    def test_cle_nir_zero_a_gauche(self):
        # Une cle < 10 doit etre zero-paddee (ex. 4 -> "04").
        assert checksum.nir_key("2750329170280") == "04"

    def test_base_non_numerique_leve_valueerror(self):
        with pytest.raises(ValueError):
            checksum.nir_key("275032917028A")


class TestIbanCheckDigits:
    def test_recompose_iban_valide(self):
        bban = "12345678901234567890123"  # 23 chiffres
        digits = checksum.iban_check_digits(bban, country="FR")
        assert iban_v.validate(f"FR{digits}{bban}")

    def test_iban_check_digits_deux_chiffres(self):
        digits = checksum.iban_check_digits("12345678901234567890123", country="FR")
        assert len(digits) == 2
        assert digits.isdigit()

    def test_iban_check_digits_mod97_un(self):
        bban = "12345678901234567890123"
        digits = checksum.iban_check_digits(bban, country="FR")
        assert mod97.iban_mod97(f"FR{digits}{bban}") == 1

    def test_bban_mauvaise_longueur_leve_valueerror(self):
        with pytest.raises(ValueError):
            checksum.iban_check_digits("123", country="FR")


class TestTvaKey:
    def test_tva_key_siren_reference(self):
        # TVA FR44732829320: SIREN 732829320 -> cle 44.
        assert checksum.tva_key("732829320") == "44"

    def test_recompose_tva_valide(self):
        siren = "732829320"
        key = checksum.tva_key(siren)
        assert tva_v.validate(f"FR{key}{siren}")

    def test_tva_key_deux_chiffres(self):
        key = checksum.tva_key("732829320")
        assert len(key) == 2
        assert key.isdigit()

    def test_siren_non_numerique_leve_valueerror(self):
        with pytest.raises(ValueError):
            checksum.tva_key("732A29320")
