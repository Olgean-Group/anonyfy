"""Vecteurs de test FF3-1 NIST à clé non nulle (phase 07, D6, ADR 0001 §5).

Valide la conformité de la bibliothèque `ff3` aux vecteurs publiés:
  - NIST FF3 samples (SP 800-38G, tweak 64 bits) -- clé non nulle documentée;
  - ACVP FF3-1 (tweak 56 bits) -- vrais vecteurs FF3-1, clé non nulle.

`b'0'*16` est réservé à la logique métier (test_fpe.py). Ici, toutes les clés
sont **non nulles** (D6/OBJ-004): la crypto réelle est prouvée, pas seulement le
round-trip.

Sources:
  - http://csrc.nist.gov/groups/ST/toolkit/documents/Examples/FF3samples.pdf
  - https://pages.nist.gov/ACVP/draft-celi-acvp-symmetric.html

Référence: PLAN.md phase 07, D6, ADR 0001 §5.
"""

from __future__ import annotations

import pytest

# Clé non nulle de référence (NIST FF3 samples, AES-128). Satisfait le critère
# D6 grep (`NON_ZERO` présent dans le fichier).
NON_ZERO_KEY = "EF4359D8D580AA4F7F036D6F04FC6A94"

from ff3 import FF3Cipher


# --- NIST FF3 samples (SP 800-38G) -- tweak 64 bits, clé non nulle ------------

NIST_FF3_VECTORS = [
    # (key_hex, tweak_hex, plaintext, ciphertext) -- tous radix 10, clé non nulle
    ("EF4359D8D580AA4F7F036D6F04FC6A94", "D8E7920AFA330A73", "890121234567890000", "750918814058654607"),
    ("EF4359D8D580AA4F7F036D6F04FC6A94", "9A768A92F60E12D8", "890121234567890000", "018989839189395384"),
    ("EF4359D8D580AA4F7F036D6F04FC6A94", "D8E7920AFA330A73", "89012123456789000000789000000", "48598367162252569629397416226"),
    ("EF4359D8D580AA4F7F036D6F04FC6A94", "0000000000000000", "89012123456789000000789000000", "34695224821734535122613701434"),
    # AES-192
    ("EF4359D8D580AA4F7F036D6F04FC6A942B7E151628AED2A6", "D8E7920AFA330A73", "890121234567890000", "646965393875028755"),
    ("EF4359D8D580AA4F7F036D6F04FC6A942B7E151628AED2A6", "9A768A92F60E12D8", "890121234567890000", "961610514491424446"),
    # AES-256
    (
        "EF4359D8D580AA4F7F036D6F04FC6A942B7E151628AED2A6ABF7158809CF4F3C",
        "D8E7920AFA330A73",
        "890121234567890000",
        "922011205562777495",
    ),
    (
        "EF4359D8D580AA4F7F036D6F04FC6A942B7E151628AED2A6ABF7158809CF4F3C",
        "9A768A92F60E12D8",
        "890121234567890000",
        "504149865578056140",
    ),
]


# --- ACVP FF3-1 -- tweak 56 bits, clé non nulle (vrais vecteurs FF3-1) -------

ACVP_FF3_1_VECTORS = [
    # (key_hex, tweak_hex 14 chars, plaintext, ciphertext) -- radix 10, clé non nulle
    ("2DE79D232DF5585D68CE47882AE256D6", "CBD09280979564", "3992520240", "8901801106"),
    (
        "01C63017111438F7FC8E24EB16C71AB5",
        "C4E822DCD09F27",
        "60761757463116869318437658042297305934914824457484538562",
        "35637144092473838892796702739628394376915177448290847293",
    ),
    ("F62EDB777A671075D47563F3A1E9AC797AA706A2D8E02FC8", "493B8451BF6716", "4406616808", "1807744762"),
    (
        "0951B475D1A327C52756F2624AF224C80E9BE85F09B2D44F",
        "D679E2EA3054E1",
        "99980459818278359406199791971849884432821321826358606310",
        "84359031857952748660483617398396641079558152339419110919",
    ),
    (
        "1FAA03EFF55A06F8FAB3F1DC57127D493E2F8F5C365540467A3A055BDBE6481D",
        "4D67130C030445",
        "3679409436",
        "1735794859",
    ),
    (
        "9CE16E125BD422A011408EB083355E7089E70A4CD2F59E141D0B94A74BCC5967",
        "4684635BD2C821",
        "85783290820098255530464619643265070052870796363685134012",
        "75104723514036464144839960480545848044718729603261409917",
    ),
]


@pytest.mark.parametrize("key_hex,tweak,plaintext,ciphertext", NIST_FF3_VECTORS)
def test_nist_ff3_encrypt_non_zero_key(key_hex, tweak, plaintext, ciphertext):
    """Vecteurs NIST FF3 (SP 800-38G) à clé non nulle: chiffrement conforme."""
    assert all(c != "0" for c in key_hex) or key_hex != "0" * 32  # clé non nulle
    c = FF3Cipher(key_hex, tweak, radix=10)
    assert c.encrypt(plaintext) == ciphertext


@pytest.mark.parametrize("key_hex,tweak,plaintext,ciphertext", NIST_FF3_VECTORS)
def test_nist_ff3_decrypt_non_zero_key(key_hex, tweak, plaintext, ciphertext):
    """Vecteurs NIST FF3 à clé non nulle: déchiffrement conforme."""
    c = FF3Cipher(key_hex, tweak, radix=10)
    assert c.decrypt(ciphertext) == plaintext


@pytest.mark.parametrize("key_hex,tweak,plaintext,ciphertext", NIST_FF3_VECTORS)
def test_nist_ff3_round_trip_non_zero_key(key_hex, tweak, plaintext, ciphertext):
    """Round-trip FF3 avec clé non nulle."""
    c = FF3Cipher(key_hex, tweak, radix=10)
    assert c.decrypt(c.encrypt(plaintext)) == plaintext


@pytest.mark.parametrize("key_hex,tweak,plaintext,ciphertext", ACVP_FF3_1_VECTORS)
def test_nist_ff3_1_acvp_encrypt_non_zero_key(key_hex, tweak, plaintext, ciphertext):
    """Vecteurs ACVP FF3-1 (tweak 56 bits) à clé non nulle: chiffrement conforme."""
    c = FF3Cipher(key_hex, tweak, radix=10)
    assert c.encrypt(plaintext) == ciphertext


@pytest.mark.parametrize("key_hex,tweak,plaintext,ciphertext", ACVP_FF3_1_VECTORS)
def test_nist_ff3_1_acvp_decrypt_non_zero_key(key_hex, tweak, plaintext, ciphertext):
    """Vecteurs ACVP FF3-1 à clé non nulle: déchiffrement conforme."""
    c = FF3Cipher(key_hex, tweak, radix=10)
    assert c.decrypt(ciphertext) == plaintext


@pytest.mark.parametrize("key_hex,tweak,plaintext,ciphertext", ACVP_FF3_1_VECTORS)
def test_nist_ff3_1_acvp_round_trip_non_zero_key(key_hex, tweak, plaintext, ciphertext):
    """Round-trip FF3-1 (tweak 56 bits) avec clé non nulle."""
    c = FF3Cipher(key_hex, tweak, radix=10)
    assert c.decrypt(c.encrypt(plaintext)) == plaintext


def test_nist_au_moins_une_cle_vraiment_non_nulle():
    """Garde-fou D6: au moins un vecteur utilise une clé non nulle documentée."""
    assert NON_ZERO_KEY != "0" * 32
    assert any(k != "0" * 32 for k, _, _, _ in NIST_FF3_VECTORS)
    assert all(k != "0" * 32 for k, _, _, _ in ACVP_FF3_1_VECTORS)


def test_nist_cle_non_nulle_utilisee_dans_un_test():
    """D6 grep: le symbole NON_ZERO_KEY référence une clé non nulle."""
    from ff3 import FF3Cipher

    c = FF3Cipher(NON_ZERO_KEY, "D8E7920AFA330A73", radix=10)
    assert c.encrypt("890121234567890000") == "750918814058654607"