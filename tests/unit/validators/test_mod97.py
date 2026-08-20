"""Tests des helpers mod 97 (phase 05).

Logique testée: reste mod 97 d'un grand nombre en chaîne, contrôle IBAN
(réarrangement + conversion lettres), clé NIR (97 - reste, gestion Corse 2A/2B).
"""

from __future__ import annotations

import pytest

from anonyfy.detect.validators.mod97 import (
    iban_mod97,
    mod97_remainder,
    nir_control_key,
)


class TestMod97Remainder:
    def test_reste_simple(self):
        assert mod97_remainder("100") == 3

    def test_grand_nombre_iban(self):
        # Reste d'un grand nombre sur plus de 15 chiffres (au-delà d'un int64).
        assert mod97_remainder("30006000011234567890189152776") == 1

    def test_lettres_rejetees(self):
        with pytest.raises(ValueError):
            mod97_remainder("12A")


class TestIbanMod97:
    def test_iban_fr_valide_plan(self):
        # IBAN FR7630006000011234567890189 (critère PLAN): reste 1.
        assert iban_mod97("FR7630006000011234567890189") == 1

    def test_iban_fr_invalide_plan(self):
        # IBAN FR7630006000011234567890180: clé fausse, reste != 1.
        assert iban_mod97("FR7630006000011234567890180") != 1

    def test_conversion_lettres_fait_15_pour_f_27_pour_r(self):
        # FR -> F=15, R=27; l'IBAN réarrangé doit donner un reste de 1.
        # Vérifie indirectement que 'A' -> 10: IBAN factice FR00AAAA... non testé,
        # on se contente du cas réel.
        assert iban_mod97("FR7630006000011234567890189") == 1


class TestNirControlKey:
    def test_nir_base_plan(self):
        # Base 2750329170280: reste 93, clé = 97 - 93 = 04.
        assert nir_control_key("2750329170280") == 4

    def test_nir_corse_2b(self):
        # 185032B001015: 2B -> 18, reste 42, clé = 55.
        assert nir_control_key("185032B001015") == 55

    def test_nir_corse_2a(self):
        # 185032A001015: 2A -> 19, reste 69, clé = 28.
        assert nir_control_key("185032A001015") == 28

    def test_nir_sans_dept_corse_passe(self):
        # Un NIR métropole ne contient ni A ni B: pas de substitution.
        assert nir_control_key("2750329170280") == 4

    def test_cle_zero_padding_implicite(self):
        # Clé 4 renvoyée comme int 4 (le formattage 2 chiffres est fait par l'appelant).
        assert isinstance(nir_control_key("2750329170280"), int)
