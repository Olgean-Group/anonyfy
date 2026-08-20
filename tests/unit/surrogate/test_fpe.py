"""Tests FPE FF3-1 sur les grands domaines (phase 07).

Valide: round-trip, déterminisme scopé, injectivité, substituts valides au
format du type, vecteurs NIST à clé non nulle (cf. test_ff3_vectors.py), cas
limites. `b'0'*16` est réservé à la logique métier; les tests crypto réels
utilisent une clé non nulle.

Référence: PLAN.md phase 07, ADR 0001 §2/§4/§5, D6, D13.
"""

from __future__ import annotations

import pytest

from anonyfy.detect.validators import cb as cb_v
from anonyfy.detect.validators import iban as iban_v
from anonyfy.detect.validators import nir as nir_v
from anonyfy.detect.validators import phone as phone_v
from anonyfy.detect.validators import siren as siren_v
from anonyfy.detect.validators import tva as tva_v
from anonyfy.surrogate import fpe

ZERO_KEY = b"0" * 16
NON_ZERO_KEY = bytes.fromhex("EF4359D8D580AA4F7F036D6F04FC6A94")
SCOPE = "dossier-47"

# Valeurs de référence valides.
SIREN = "732829320"
SIRET = "73282932000033"
NIR = "275032917028004"
IBAN = "FR4812345678901234567890123"
TVA = "FR44732829320"
CB = "4111111111111111"
PHONE_NAT = "0612345678"
PHONE_INT = "+33612345678"


# --- Round-trip (logique métier, clé nulle acceptable) ----------------------


@pytest.mark.parametrize(
    "value,enc,dec",
    [
        (SIREN, fpe.encrypt_siren, fpe.decrypt_siren),
        (SIRET, fpe.encrypt_siret, fpe.decrypt_siret),
        (NIR, fpe.encrypt_nir, fpe.decrypt_nir),
        (IBAN, fpe.encrypt_iban, fpe.decrypt_iban),
        (TVA, fpe.encrypt_tva, fpe.decrypt_tva),
        (CB, fpe.encrypt_cb, fpe.decrypt_cb),
        (PHONE_NAT, fpe.encrypt_phone, fpe.decrypt_phone),
        (PHONE_INT, fpe.encrypt_phone, fpe.decrypt_phone),
    ],
)
def test_round_trip_cle_nulle(value, enc, dec):
    c = enc(value, key=ZERO_KEY, scope=SCOPE)
    assert dec(c, key=ZERO_KEY, scope=SCOPE) == value


def test_round_trip_siret_reference_plan():
    # PLAN phase 07: la reference SIRET est 73282932000035, qui n'est PAS Luhn-valide
    # (le chiffre de controle correct du corps 7328293200003 est 3 -> 73282932000033).
    # Coquille factuelle du PLAN (cf. D16 pour le NIR): on documente et on round-trip
    # sur le SIRET valide. Le round-trip d'un SIRET invalide n'est pas garanti par
    # construction (recalcul Luhn du chiffre de controle).
    c = fpe.encrypt_siret("73282932000033", key=ZERO_KEY, scope="s")
    assert fpe.decrypt_siret(c, key=ZERO_KEY, scope="s") == "73282932000033"


def test_siret_invalide_substitut_tout_de_meme_valide():
    # Un SIRET d'entree invalide (cle Luhn fausse) produit un substitut valide:
    # on chiffre le corps et on recale la cle. Le round-trip exact n'est pas
    # garanti pour une entree invalide (le chiffre de controle est recalcule).
    c = fpe.encrypt_siret("73282932000035", key=ZERO_KEY, scope="s")
    assert siren_v.validate_siret(c)


def test_round_trip_nir_reference_plan_d16():
    # D16: NIR de référence corrigé 275032917028004.
    c = fpe.encrypt_nir("275032917028004", key=ZERO_KEY, scope="s")
    assert fpe.decrypt_nir(c, key=ZERO_KEY, scope="s") == "275032917028004"


# --- Round-trip avec clé non nulle (crypto réelle) --------------------------


@pytest.mark.parametrize(
    "value,enc,dec",
    [
        (SIREN, fpe.encrypt_siren, fpe.decrypt_siren),
        (SIRET, fpe.encrypt_siret, fpe.decrypt_siret),
        (NIR, fpe.encrypt_nir, fpe.decrypt_nir),
        (IBAN, fpe.encrypt_iban, fpe.decrypt_iban),
        (TVA, fpe.encrypt_tva, fpe.decrypt_tva),
        (CB, fpe.encrypt_cb, fpe.decrypt_cb),
        (PHONE_NAT, fpe.encrypt_phone, fpe.decrypt_phone),
    ],
)
def test_round_trip_cle_non_nulle(value, enc, dec):
    c = enc(value, key=NON_ZERO_KEY, scope=SCOPE)
    assert dec(c, key=NON_ZERO_KEY, scope=SCOPE) == value


# --- Substitut valide au format du type --------------------------------------


def test_substitut_siren_valide():
    c = fpe.encrypt_siren(SIREN, key=ZERO_KEY, scope=SCOPE)
    assert siren_v.validate(c)


def test_substitut_siret_valide():
    c = fpe.encrypt_siret(SIRET, key=ZERO_KEY, scope=SCOPE)
    assert siren_v.validate_siret(c)


def test_substitut_siret_reference_plan_valide():
    # Intention du PLAN critère 2 (validate_siret, cf. coquille signalée).
    c = fpe.encrypt_siret("73282932000035", key=ZERO_KEY, scope="s")
    assert siren_v.validate_siret(c)


def test_substitut_nir_valide():
    c = fpe.encrypt_nir(NIR, key=ZERO_KEY, scope=SCOPE)
    assert nir_v.validate(c)


def test_substitut_iban_valide():
    c = fpe.encrypt_iban(IBAN, key=ZERO_KEY, scope=SCOPE)
    assert iban_v.validate(c)


def test_substitut_tva_valide():
    c = fpe.encrypt_tva(TVA, key=ZERO_KEY, scope=SCOPE)
    assert tva_v.validate(c)


def test_substitut_cb_valide():
    c = fpe.encrypt_cb(CB, key=ZERO_KEY, scope=SCOPE)
    assert cb_v.validate(c)


def test_substitut_phone_national_valide():
    c = fpe.encrypt_phone(PHONE_NAT, key=ZERO_KEY, scope=SCOPE)
    assert phone_v.validate(c)


def test_substitut_phone_international_valide():
    c = fpe.encrypt_phone(PHONE_INT, key=ZERO_KEY, scope=SCOPE)
    assert phone_v.validate(c)


# --- Déterminisme scopé ------------------------------------------------------


@pytest.mark.parametrize("enc,dec", [(fpe.encrypt_siren, fpe.decrypt_siren)])
def test_determinisme_meme_entree_meme_sortie(enc, dec):
    a = enc(SIREN, key=ZERO_KEY, scope=SCOPE)
    b = enc(SIREN, key=ZERO_KEY, scope=SCOPE)
    assert a == b


def test_determinisme_tous_types():
    pairs = [
        (fpe.encrypt_siren, SIREN),
        (fpe.encrypt_siret, SIRET),
        (fpe.encrypt_nir, NIR),
        (fpe.encrypt_iban, IBAN),
        (fpe.encrypt_tva, TVA),
        (fpe.encrypt_cb, CB),
        (fpe.encrypt_phone, PHONE_NAT),
    ]
    for enc, value in pairs:
        assert enc(value, key=ZERO_KEY, scope=SCOPE) == enc(value, key=ZERO_KEY, scope=SCOPE)


def test_scope_change_le_substitut():
    a = fpe.encrypt_siret(SIRET, key=ZERO_KEY, scope="scope-A")
    b = fpe.encrypt_siret(SIRET, key=ZERO_KEY, scope="scope-B")
    assert a != b


def test_cle_change_le_substitut():
    a = fpe.encrypt_siret(SIRET, key=ZERO_KEY, scope=SCOPE)
    b = fpe.encrypt_siret(SIRET, key=NON_ZERO_KEY, scope=SCOPE)
    assert a != b


# --- Injectivité dans le scope ----------------------------------------------


@pytest.mark.parametrize(
    "enc,values",
    [
        (fpe.encrypt_siren, ["732829320", "123456784"]),  # 2e SIREN valide
        (fpe.encrypt_siret, ["73282932000033", "12345678901234"]),
    ],
)
def test_injectivite_deux_clairs_distincts(enc, values):
    subs = {enc(v, key=ZERO_KEY, scope=SCOPE) for v in values}
    assert len(subs) == len(values)


def test_injectivite_nir():
    subs = {fpe.encrypt_nir(v, key=ZERO_KEY, scope=SCOPE) for v in [NIR, "123456789012317"]}
    assert len(subs) == 2


def test_injectivite_cb_plusieurs():
    pans = ["4111111111111111", "5500000000000004", "4012888888881881"]
    subs = {fpe.encrypt_cb(v, key=ZERO_KEY, scope=SCOPE) for v in pans}
    assert len(subs) == len(pans)


# --- Conservation de la longueur -------------------------------------------


def test_siret_conserve_la_longueur():
    c = fpe.encrypt_siret(SIRET, key=ZERO_KEY, scope=SCOPE)
    assert len(c) == 14


def test_nir_conserve_la_longueur():
    c = fpe.encrypt_nir(NIR, key=ZERO_KEY, scope=SCOPE)
    assert len(c) == 15


def test_iban_conserve_la_longueur():
    c = fpe.encrypt_iban(IBAN, key=ZERO_KEY, scope=SCOPE)
    assert len(c) == 27


def test_phone_national_conserve_la_longueur():
    c = fpe.encrypt_phone(PHONE_NAT, key=ZERO_KEY, scope=SCOPE)
    assert len(c) == 10


def test_phone_international_conserve_la_longueur():
    c = fpe.encrypt_phone(PHONE_INT, key=ZERO_KEY, scope=SCOPE)
    assert len(c) == 12


# --- Cas limites / erreurs --------------------------------------------------


def test_siren_trop_court_leve_domain_too_small():
    # SIREN à 5 chiffres: corps 4 < minLen FF3-1 (6). Domaine effectif < 1M.
    with pytest.raises(fpe.DomainTooSmallError):
        fpe.encrypt_siren("12345", key=ZERO_KEY, scope=SCOPE)


def test_cb_trop_court_leve_domain_too_small():
    # PAN 13 chiffres: corps 12 >= 6, OK. Mais 7 chiffres: corps 6 >= 6 OK limite.
    # Pour declencher DomainTooSmall, il faut un PAN trop court.
    with pytest.raises(fpe.DomainTooSmallError):
        fpe.encrypt_cb("12345", key=ZERO_KEY, scope=SCOPE)


def test_nir_corse_non_supporte_leve_valueerror():
    # NIR Corse (2A/2B): FPE pur sur digits non réversible; registre phase 13.
    with pytest.raises(ValueError):
        fpe.encrypt_nir("2732A9117028005", key=ZERO_KEY, scope=SCOPE)


def test_cle_mauvaise_longueur_leve_valueerror():
    with pytest.raises(ValueError):
        fpe.encrypt_siret(SIRET, key=b"0" * 8, scope=SCOPE)


def test_siren_format_invalide_leve_valueerror():
    with pytest.raises(ValueError):
        fpe.encrypt_siren("123A5678", key=ZERO_KEY, scope=SCOPE)


def test_decrypt_avec_mauvaise_cle_ne_renvoie_pas_original():
    c = fpe.encrypt_siret(SIRET, key=ZERO_KEY, scope=SCOPE)
    # Une autre clé déchiffre en autre chose; le round-trip croisé échoue.
    assert fpe.decrypt_siret(c, key=NON_ZERO_KEY, scope=SCOPE) != SIRET


# --- Préfixe téléphone préservé --------------------------------------------


def test_phone_national_prefixe_0_preserve():
    c = fpe.encrypt_phone(PHONE_NAT, key=ZERO_KEY, scope=SCOPE)
    assert c.startswith("0")


def test_phone_international_prefixe_plus33_preserve():
    c = fpe.encrypt_phone(PHONE_INT, key=ZERO_KEY, scope=SCOPE)
    assert c.startswith("+33")