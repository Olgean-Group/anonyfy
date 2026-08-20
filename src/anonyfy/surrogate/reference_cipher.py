"""Cipher référence de dossier par XOR keystream (D2, D22).

Domaine générique non énumérable: XOR keystream HMAC-SHA256 (compteur de blocs).
Substitut = hex(bytes_clair XOR keystream). Longueur préservée en bytes.
Token hex non format-valide (accepté ADR §4.2 pour petit domaine générique).

D2: référence de dossier relève du mécanisme registre. Ici XOR keystream keyé.

Réversibilité: pas de clair stocké. ``decrypt`` régénère le keystream (même
key/scope/len) et XOR inverse.
"""

from __future__ import annotations

import hashlib
import hmac

_ENTITY_TYPE = "reference"


def _keystream(key: bytes, scope: str, length: int) -> bytes:
    """Génère un keystream de `length` bytes via HMAC-SHA256 en compteur."""
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


class ReferenceCipher:
    """XOR keystream keyé pour référence de dossier.

    Args:
        key: clé secrète.
        scope: identifiant de scope (déterminisme scopé).
    """

    def __init__(self, key: bytes, scope: str) -> None:
        self._key = key
        self._scope = scope

    def encrypt(self, value: str) -> str:
        """Retourne le substitut en hex (longueur bytes préservée)."""
        clear_bytes = value.encode("utf-8")
        if not clear_bytes:
            return ""
        ks = _keystream(self._key, self._scope, len(clear_bytes))
        sub_bytes = _xor(clear_bytes, ks)
        return sub_bytes.hex()

    def decrypt(self, substitute: str) -> str | None:
        """Retourne la référence claire, ou None si hex invalide."""
        if substitute == "":
            return ""
        try:
            sub_bytes = bytes.fromhex(substitute)
        except ValueError:
            return None
        ks = _keystream(self._key, self._scope, len(sub_bytes))
        clear_bytes = _xor(sub_bytes, ks)
        return clear_bytes.decode("utf-8")


__all__ = ["ReferenceCipher"]
