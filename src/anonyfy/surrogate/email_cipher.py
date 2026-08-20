"""Cipher email local-part par permutation (D9, D22).

Normalisation NFKC + minuscules du local-part. Alphabet effectif
``a-z0-9.+-'`` (38 caractères). Permutation keyée sur [0, 38^L) où L est la
longueur du local-part régularisé. Longueur préservée.

Repli keystream (XOR HMAC-SHA256) pour:
- L < 4 (domaine trop petit pour Feistel);
- local-part contenant un caractère hors alphabet (accents, etc.).
Le mode ("perm" ou "keystream") est retourné par ``encrypt`` et requis par
``decrypt`` (stocké dans le registre au mask).

Domaine en clair (casse préservée). Round-trip sur la forme régularisée du
local-part (D9 limite documentée: la forme originale "Jean.O'Brien" est
régularisée en "jean.o'brien", non récupérable).
"""

from __future__ import annotations

import hashlib
import hmac
import unicodedata

from anonyfy.surrogate.permutation import Permutation

_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789.+-'"
_BASE = len(_ALPHABET)  # 38
_CHAR_INDEX = {ch: i for i, ch in enumerate(_ALPHABET)}
_MIN_PERM_LEN = 4
_ENTITY_TYPE = "email"


def _normalize(localpart: str) -> str:
    return unicodedata.normalize("NFKC", localpart).casefold()


def _encode_base38(s: str) -> int:
    """Encode une chaîne de l'alphabet en entier (big-endian)."""
    value = 0
    for ch in s:
        value = value * _BASE + _CHAR_INDEX[ch]
    return value


def _decode_base38(value: int, length: int) -> str:
    """Décode un entier en chaîne de longueur `length` (big-endian, zero-pad)."""
    chars = []
    for _ in range(length):
        chars.append(_ALPHABET[value % _BASE])
        value //= _BASE
    return "".join(reversed(chars))


def _keystream(key: bytes, scope: str, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        msg = (
            scope.encode("utf-8")
            + b"|"
            + _ENTITY_TYPE.encode("utf-8")
            + b"|"
            + counter.to_bytes(8, "big")
        )
        out.extend(hmac.new(key, msg, hashlib.sha256).digest())
        counter += 1
    return bytes(out[:length])


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b, strict=True))


class EmailCipher:
    """Permutation keyée du local-part email (D9).

    Args:
        key: clé secrète.
        scope: identifiant de scope (déterminisme scopé).
    """

    def __init__(self, key: bytes, scope: str) -> None:
        self._key = key
        self._scope = scope

    def encrypt(self, email: str) -> tuple[str, str]:
        """Retourne (substitute, mode). mode = "perm" ou "keystream"."""
        localpart, _, domaine = email.partition("@")
        if not domaine:
            # Pas de domaine: on traite tout comme local-part, pas un email valide
            return email, "keystream"
        norm = _normalize(localpart)
        if len(norm) >= _MIN_PERM_LEN and all(ch in _CHAR_INDEX for ch in norm):
            return self._encrypt_perm(norm, domaine), "perm"
        return self._encrypt_keystream(norm, domaine), "keystream"

    def _encrypt_perm(self, norm: str, domaine: str) -> str:
        n = _BASE ** len(norm)
        perm = Permutation(key=self._key, scope=self._scope, entity_type=_ENTITY_TYPE, n=n)
        value = _encode_base38(norm)
        sub_value = perm.encrypt(value)
        sub_localpart = _decode_base38(sub_value, len(norm))
        return f"{sub_localpart}@{domaine}"

    def _encrypt_keystream(self, norm: str, domaine: str) -> str:
        clear_bytes = norm.encode("utf-8")
        if not clear_bytes:
            return f"@{domaine}"
        ks = _keystream(self._key, self._scope, len(clear_bytes))
        sub_bytes = _xor(clear_bytes, ks)
        return f"{sub_bytes.hex()}@{domaine}"

    def decrypt(self, substitute: str, mode: str) -> str:
        """Retourne l'email clair (forme régularisée du local-part)."""
        sub_localpart, _, domaine = substitute.partition("@")
        if mode == "perm":
            n = _BASE ** len(sub_localpart)
            perm = Permutation(key=self._key, scope=self._scope, entity_type=_ENTITY_TYPE, n=n)
            sub_value = _encode_base38(sub_localpart)
            value = perm.decrypt(sub_value)
            localpart = _decode_base38(value, len(sub_localpart))
            return f"{localpart}@{domaine}"
        # keystream
        sub_bytes = bytes.fromhex(sub_localpart)
        ks = _keystream(self._key, self._scope, len(sub_bytes))
        clear_bytes = _xor(sub_bytes, ks)
        localpart = clear_bytes.decode("utf-8")
        return f"{localpart}@{domaine}"


__all__ = ["EmailCipher"]
