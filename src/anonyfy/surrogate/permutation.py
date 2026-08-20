"""Permutation keyée Feistel (D22).

Permutation bijective sur [0, n) inversible, déterminisme scopé
(key + scope + entity_type). Réseau de Feistel sur domaine 2^k >= n,
cycle-walking pour n non puissance de 2. Stdlib uniquement (hmac, hashlib).

Isolation: seul ce module connaît la construction Feistel (analogue fpe.py
pour FF3-1).
"""

from __future__ import annotations

import hashlib
import hmac

_ROUNDS = 10


class Permutation:
    """Permutation bijective keyée sur [0, n).

    Args:
        key: clé secrète (bytes).
        scope: identifiant de scope (déterminisme scopé, invariant 2).
        entity_type: type d'entité (injectivité par type).
        n: taille du domaine. x,y ∈ [0, n).
    """

    def __init__(self, key: bytes, scope: str, entity_type: str, n: int) -> None:
        if n < 1:
            raise ValueError(f"n doit etre >= 1, recu {n}")
        self._key = key
        self._scope = scope
        self._entity_type = entity_type
        self._n = n
        # k = nombre de bits pour couvrir [0, n). 2^k >= n.
        k = 1
        while (1 << k) < n:
            k += 1
        self._k = k
        # Deux moitiés sur k bits (total 2k bits, domaine 2^(2k) >= 2^k >= n).
        self._half_bits = k
        self._half_mask = (1 << k) - 1
        self._block_size = (1 << k)  # taille d'une moitié = 2^k

    def _round_function(self, right: int, round_index: int) -> int:
        """F(R) = int.from_bytes(HMAC-SHA256(key, scope||type||round||R), 'big') mod block_size."""
        msg = (
            self._scope.encode("utf-8")
            + b"|"
            + self._entity_type.encode("utf-8")
            + b"|"
            + round_index.to_bytes(4, "big")
            + b"|"
            + right.to_bytes((self._half_bits + 7) // 8 or 1, "big")
        )
        digest = hmac.new(self._key, msg, hashlib.sha256).digest()
        return int.from_bytes(digest, "big") % self._block_size

    def _feistel_block(self, x: int) -> int:
        """Un passage complet du réseau de Feistel sur x ∈ [0, 2^(2k)).

        x décomposé en (L, R) chacun sur k bits. 10 rounds.
        """
        L = x >> self._half_bits
        R = x & self._half_mask
        for r in range(_ROUNDS):
            f = self._round_function(R, r)
            new_L = R
            new_R = L ^ f
            L, R = new_L, new_R & self._half_mask
        # Recombiner: L occupe les bits hauts, R les bas
        return (L << self._half_bits) | R

    def _feistel_block_inverse(self, y: int) -> int:
        """Inverse du réseau de Feistel (rounds en ordre inverse)."""
        L = y >> self._half_bits
        R = y & self._half_mask
        for r in range(_ROUNDS - 1, -1, -1):
            # Inverse: (L, R) <- (R xor F(L), L)
            f = self._round_function(L, r)
            prev_R = L
            prev_L = R ^ f
            L, R = prev_L & self._half_mask, prev_R
        return (L << self._half_bits) | R

    def _check_domain(self, x: int, label: str) -> None:
        if x < 0 or x >= self._n:
            raise ValueError(f"{label} hors domaine [0,{self._n}): {x}")

    def encrypt(self, x: int) -> int:
        """Permute x ∈ [0, n) -> y ∈ [0, n). Cycle-walking si besoin."""
        self._check_domain(x, "x")
        if self._n == 1:
            return 0
        y = self._feistel_block(x)
        while y >= self._n:
            y = self._feistel_block(y)
        return y

    def decrypt(self, y: int) -> int:
        """Inverse de encrypt: y ∈ [0, n) -> x ∈ [0, n)."""
        self._check_domain(y, "y")
        if self._n == 1:
            return 0
        x = self._feistel_block_inverse(y)
        while x >= self._n:
            x = self._feistel_block_inverse(x)
        return x
