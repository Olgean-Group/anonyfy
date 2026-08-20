"""Wrapper FPE FF3-1 pour les grands domaines (phase 07).

Isole la dépendance `ff3` derrière ce module unique (D13, ADR 0001 §2): aucune
autre partie du cœur n'importe `ff3`. Le remplacement de la bibliothèque touche
exclusivement ce fichier.

Pour chaque type à grand domaine (D2: NIR, SIREN, SIRET, IBAN, TVA, carte
bancaire, téléphone), on chiffre le corps significatif par FF3-1 (radix 10), on
recale la clé de contrôle (Luhn, mod 97 NIR, mod 97 IBAN, clé TVA) pour que le
substitut soit **valide au format**, et on préserve les préfixes/digits à
contrainte de format pour garantir la bijectivité.

Le tweak FF3-1 (56 bits) est dérivé du scope via HMAC-SHA256(key, scope) pour
lier le substitut à son scope (déterminisme scopé, PRD F4). `b'0'*16` est
accepté pour la logique métier; la validation crypto réelle utilise une clé
non nulle (cf. test_ff3_vectors.py, D6).

Référence: PLAN.md phase 07, ADR 0001 §2/§4/§5, D2, D6, D13.
"""

from __future__ import annotations

import hashlib
import hmac

from ff3 import FF3Cipher

from anonyfy.surrogate import checksum

__all__ = [
    "DomainTooSmallError",
    "decrypt_cb",
    "decrypt_iban",
    "decrypt_nir",
    "decrypt_phone",
    "decrypt_siren",
    "decrypt_siret",
    "decrypt_tva",
    "encrypt_cb",
    "encrypt_iban",
    "encrypt_nir",
    "encrypt_phone",
    "encrypt_siren",
    "encrypt_siret",
    "encrypt_tva",
]

# FF3-1 impose radix^minLen >= 1 000 000; pour radix 10, minLen = 6.
_MIN_BODY_LEN = 6
_MAX_BODY_LEN = 56  # 2 * floor(96 / log2(10))
_MAX_ITER = 256


class DomainTooSmallError(Exception):
    """Le domaine effectif est en-dessous du seuil FF3-1 (1M).

    Le type concerné doit basculer sur le mécanisme registre (phase 10/13) plutôt
    que sur FPE pur (D2, ADR 0001 §4.2). Documenté, ne bascule pas silencieusement.
    """


def _key_hex(key: bytes) -> str:
    if not isinstance(key, (bytes, bytearray)):
        raise ValueError(f"clé attendue en bytes, reçu {type(key).__name__}")
    if len(key) not in (16, 24, 32):
        raise ValueError(f"longueur de clé {len(key)} invalide: 16, 24 ou 32 bytes requis")
    return bytes(key).hex()


def _tweak_hex(scope: str, key: bytes, counter: int) -> str:
    """Tweak FF3-1 (56 bits = 14 hex) dérivé du scope et du compteur via HMAC.

    Le compteur permet de re-chiffrer avec un tweak différent si le résultat
    précédent viole une contrainte de format (borné, cf. ADR 0001 §2).
    """
    msg = scope.encode("utf-8") + counter.to_bytes(4, "big")
    return hmac.new(key, msg, hashlib.sha256).digest()[:7].hex()


def _cipher(key_hex: str, tweak_hex: str) -> FF3Cipher:
    return FF3Cipher(key_hex, tweak_hex, radix=10)


def _check_body_len(body_len: int, type_label: str) -> None:
    if body_len < _MIN_BODY_LEN:
        raise DomainTooSmallError(
            f"domaine effectif de {type_label} ({body_len} chiffres) < seuil FF3-1 "
            f"({_MIN_BODY_LEN}); bascule sur le mécanisme registre (phase 10/13)"
        )
    if body_len > _MAX_BODY_LEN:
        raise ValueError(f"corps de {type_label} trop long pour FF3-1: {body_len}")


def _require_digits(value: str, label: str) -> None:
    if not value or not value.isdigit():
        raise ValueError(f"{label} non numérique ou vide: {value!r}")


# --- SIREN / SIRET / carte bancaire (Luhn) -----------------------------------


def _encrypt_luhn_type(value: str, total_len: int, key: bytes, scope: str, label: str) -> str:
    _require_digits(value, label)
    if len(value) < total_len:
        raise DomainTooSmallError(
            f"{label} de longueur {len(value)} < {total_len} attendus; "
            f"domaine effectif sous le seuil FF3-1 (mécanisme registre, phase 10/13)"
        )
    if len(value) > total_len:
        raise ValueError(f"{label} de longueur {len(value)} > {total_len} attendus")
    body = value[: total_len - 1]
    _check_body_len(len(body), label)
    kh = _key_hex(key)
    enc = _cipher(kh, _tweak_hex(scope, key, 0)).encrypt(body)
    return enc + str(checksum.luhn_check_digit(enc))


def _decrypt_luhn_type(ciphertext: str, total_len: int, key: bytes, scope: str, label: str) -> str:
    _require_digits(ciphertext, label)
    if len(ciphertext) != total_len:
        raise ValueError(f"{label} chiffré de longueur {len(ciphertext)} != {total_len}")
    body = ciphertext[: total_len - 1]
    kh = _key_hex(key)
    plain = _cipher(kh, _tweak_hex(scope, key, 0)).decrypt(body)
    return plain + str(checksum.luhn_check_digit(plain))


def encrypt_siren(value: str, *, key: bytes, scope: str) -> str:
    """Chiffre un SIREN (9 chiffres) en un SIREN Luhn-valide."""
    return _encrypt_luhn_type(value, 9, key, scope, "SIREN")


def decrypt_siren(ciphertext: str, *, key: bytes, scope: str) -> str:
    return _decrypt_luhn_type(ciphertext, 9, key, scope, "SIREN")


def encrypt_siret(value: str, *, key: bytes, scope: str) -> str:
    """Chiffre un SIRET (14 chiffres) en un SIRET Luhn-valide."""
    return _encrypt_luhn_type(value, 14, key, scope, "SIRET")


def decrypt_siret(ciphertext: str, *, key: bytes, scope: str) -> str:
    return _decrypt_luhn_type(ciphertext, 14, key, scope, "SIRET")


def encrypt_cb(value: str, *, key: bytes, scope: str) -> str:
    """Chiffre un PAN (13 à 19 chiffres) en un PAN Luhn-valide."""
    _require_digits(value, "PAN")
    if len(value) < 13:
        raise DomainTooSmallError(
            f"PAN de longueur {len(value)} < 13; domaine effectif sous le seuil "
            f"FF3-1 (mécanisme registre, phase 10/13)"
        )
    if len(value) > 19:
        raise ValueError(f"PAN de longueur {len(value)} > 19")
    body = value[:-1]
    _check_body_len(len(body), "PAN")
    kh = _key_hex(key)
    enc = _cipher(kh, _tweak_hex(scope, key, 0)).encrypt(body)
    return enc + str(checksum.luhn_check_digit(enc))


def decrypt_cb(ciphertext: str, *, key: bytes, scope: str) -> str:
    _require_digits(ciphertext, "PAN")
    if not (13 <= len(ciphertext) <= 19):
        raise ValueError(f"PAN chiffré de longueur {len(ciphertext)} hors [13, 19]")
    body = ciphertext[:-1]
    kh = _key_hex(key)
    plain = _cipher(kh, _tweak_hex(scope, key, 0)).decrypt(body)
    return plain + str(checksum.luhn_check_digit(plain))


# --- NIR (mod 97, premier chiffre [1-9] préservé) ---------------------------


def _normalize_nir_body(value: str) -> str:
    """Valide le NIR et renvoie les 13 chiffres significatifs.

    Le NIR Corse (2A/2B) n'est pas réversible par FPE sur digits; lève
    ValueError et renvoie au mécanisme registre (phase 13).
    """
    if "2A" in value or "2B" in value:
        raise ValueError(
            "NIR Corse (2A/2B) non supporté par FPE pur en phase 07; "
            "voir mécanisme registre (phase 13)"
        )
    _require_digits(value, "NIR")
    if len(value) < 15:
        raise DomainTooSmallError(
            f"NIR de longueur {len(value)} < 15; domaine effectif sous le seuil "
            f"FF3-1 (mécanisme registre, phase 10/13)"
        )
    if len(value) != 15:
        raise ValueError(f"NIR de longueur {len(value)} != 15")
    if value[0] not in "12":
        raise ValueError(f"premier chiffre NIR invalide: {value[0]!r}")
    return value[:13]


def encrypt_nir(value: str, *, key: bytes, scope: str) -> str:
    """Chiffre un NIR (15 caractères) en un NIR à clé mod 97 valide.

    Le premier chiffre (sexe, [1-9]) est préservé pour garantir la validité
    format sans itération; FPE opère sur les 12 chiffres suivants.
    """
    base13 = _normalize_nir_body(value)
    first = base13[0]
    body = base13[1:]  # 12 chiffres
    _check_body_len(len(body), "NIR")
    kh = _key_hex(key)
    enc = _cipher(kh, _tweak_hex(scope, key, 0)).encrypt(body)
    enc_base = first + enc
    return enc_base + checksum.nir_key(enc_base)


def decrypt_nir(ciphertext: str, *, key: bytes, scope: str) -> str:
    if "2A" in ciphertext or "2B" in ciphertext:
        raise ValueError("NIR Corse (2A/2B) non supporté par FPE pur en phase 07")
    _require_digits(ciphertext, "NIR")
    if len(ciphertext) != 15:
        raise ValueError(f"NIR chiffré de longueur {len(ciphertext)} != 15")
    first = ciphertext[0]
    enc = ciphertext[1:13]
    kh = _key_hex(key)
    plain = _cipher(kh, _tweak_hex(scope, key, 0)).decrypt(enc)
    plain_base = first + plain
    return plain_base + checksum.nir_key(plain_base)


# --- IBAN France (mod 97) ---------------------------------------------------


def encrypt_iban(value: str, *, key: bytes, scope: str) -> str:
    """Chiffre un IBAN FR (27 caractères) en un IBAN FR à clé mod 97 valide."""
    if not value.startswith("FR"):
        raise ValueError(f"IBAN non FR: {value!r}")
    rest = value[2:]
    _require_digits(rest, "IBAN (après FR)")
    if len(value) < 27:
        raise DomainTooSmallError(
            f"IBAN de longueur {len(value)} < 27; domaine effectif sous le seuil "
            f"FF3-1 (mécanisme registre, phase 10/13)"
        )
    if len(value) != 27:
        raise ValueError(f"IBAN FR de longueur {len(value)} != 27")
    bban = value[4:]  # 23 chiffres
    _check_body_len(len(bban), "IBAN")
    kh = _key_hex(key)
    enc_bban = _cipher(kh, _tweak_hex(scope, key, 0)).encrypt(bban)
    return "FR" + checksum.iban_check_digits(enc_bban, country="FR") + enc_bban


def decrypt_iban(ciphertext: str, *, key: bytes, scope: str) -> str:
    if not ciphertext.startswith("FR"):
        raise ValueError(f"IBAN chiffré non FR: {ciphertext!r}")
    if len(ciphertext) != 27:
        raise ValueError(f"IBAN chiffré de longueur {len(ciphertext)} != 27")
    enc_bban = ciphertext[4:]
    _require_digits(enc_bban, "IBAN chiffré (BBAN)")
    kh = _key_hex(key)
    plain_bban = _cipher(kh, _tweak_hex(scope, key, 0)).decrypt(enc_bban)
    return "FR" + checksum.iban_check_digits(plain_bban, country="FR") + plain_bban


# --- TVA intracommunautaire FR (clé SIREN) -----------------------------------


def encrypt_tva(value: str, *, key: bytes, scope: str) -> str:
    """Chiffre un numéro TVA FR (13 caractères) en un TVA FR à clé valide."""
    if not value.startswith("FR"):
        raise ValueError(f"TVA non FR: {value!r}")
    rest = value[2:]
    _require_digits(rest, "TVA (après FR)")
    if len(value) < 13:
        raise DomainTooSmallError(
            f"TVA de longueur {len(value)} < 13; domaine effectif sous le seuil "
            f"FF3-1 (mécanisme registre, phase 10/13)"
        )
    if len(value) != 13:
        raise ValueError(f"TVA FR de longueur {len(value)} != 13")
    siren = value[4:]  # 9 chiffres
    _check_body_len(len(siren), "TVA")
    kh = _key_hex(key)
    enc_siren = _cipher(kh, _tweak_hex(scope, key, 0)).encrypt(siren)
    return "FR" + checksum.tva_key(enc_siren) + enc_siren


def decrypt_tva(ciphertext: str, *, key: bytes, scope: str) -> str:
    if not ciphertext.startswith("FR"):
        raise ValueError(f"TVA chiffrée non FR: {ciphertext!r}")
    if len(ciphertext) != 13:
        raise ValueError(f"TVA chiffrée de longueur {len(ciphertext)} != 13")
    enc_siren = ciphertext[4:]
    _require_digits(enc_siren, "TVA chiffrée (SIREN)")
    kh = _key_hex(key)
    plain_siren = _cipher(kh, _tweak_hex(scope, key, 0)).decrypt(enc_siren)
    return "FR" + checksum.tva_key(plain_siren) + plain_siren


# --- Téléphone FR (préfixe + premier chiffre significatif préservés) --------


def _phone_parts(value: str) -> tuple[str, str]:
    """Renvoie (préfixe, corps 9 chiffres) pour un téléphone FR.

    Le premier chiffre significatif ([1-9]) est préservé pour garantir la
    validité du format sans itération; FPE opère sur les 8 chiffres restants.
    """
    if value.startswith("+33"):
        rest = value[3:]
        prefix = "+33"
    elif value.startswith("0"):
        rest = value[1:]
        prefix = "0"
    else:
        raise ValueError(f"téléphone FR attendu (0… ou +33…): {value!r}")
    _require_digits(rest, "téléphone")
    if len(value) < (4 if prefix == "+33" else 10):
        raise DomainTooSmallError(
            f"téléphone de longueur {len(value)} trop court; domaine effectif sous "
            f"le seuil FF3-1 (mécanisme registre, phase 10/13)"
        )
    if len(rest) != 9:
        raise ValueError(f"téléphone FR: 9 chiffres significatifs attendus, reçu {len(rest)}")
    if rest[0] not in "123456789":
        raise ValueError(f"premier chiffre significatif du téléphone invalide: {rest[0]!r}")
    return prefix, rest


def encrypt_phone(value: str, *, key: bytes, scope: str) -> str:
    """Chiffre un téléphone FR en un téléphone FR valide (préfixe préservé)."""
    prefix, rest = _phone_parts(value)
    first_sig = rest[0]
    body = rest[1:]  # 8 chiffres
    _check_body_len(len(body), "téléphone")
    kh = _key_hex(key)
    enc = _cipher(kh, _tweak_hex(scope, key, 0)).encrypt(body)
    return prefix + first_sig + enc


def decrypt_phone(ciphertext: str, *, key: bytes, scope: str) -> str:
    prefix, rest = _phone_parts(ciphertext)
    first_sig = rest[0]
    enc = rest[1:]
    kh = _key_hex(key)
    plain = _cipher(kh, _tweak_hex(scope, key, 0)).decrypt(enc)
    return prefix + first_sig + plain