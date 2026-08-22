"""Algorithme de Luhn (phase 05).

Somme de contrôle de Luhn utilisée par SIREN, SIRET et carte bancaire.
L'algorithme: de droite à gauche, on double un chiffre sur deux (en partant du
second chiffre); si le doublement dépasse 9, on soustrait 9; la somme modulo 10
doit valoir 0.

Référence: PLAN.md phase 05, PRD §7 (SIREN/SIRET/carte bancaire).
"""

from __future__ import annotations

__all__ = ["is_valid_luhn", "luhn_checksum"]

# Phase 32 — M4: table précalculée des contributions de Luhn par paire de
# chiffres. Pour une paire (a, b) où a est en position paire (non doublée) et b
# en position impaire (doublée), contribution = a + (2*b si 2*b<=9 else 2*b-9).
# Traitement par paires (depuis la droite) => moitié d'itérations, lookup table
# au lieu de calculs par caractère.
_LUHN_PAIR: tuple[int, ...] = tuple(
    a + (2 * b if 2 * b <= 9 else 2 * b - 9) for a in range(10) for b in range(10)
)
_ORD0 = ord("0")


def luhn_checksum(digits: str) -> int:
    """Renvoie la somme de contrôle de Luhn modulo 10 d'une chaîne de chiffres.

    Lève ValueError si la chaîne contient autre chose que des chiffres ou est vide.
    """
    if not digits or not digits.isdigit():
        raise ValueError(f"chaîne non numérique ou vide: {digits!r}")
    rev = digits[::-1]
    n = len(rev)
    total = 0
    pair = _LUHN_PAIR
    for i in range(0, n - 1, 2):
        total += pair[(ord(rev[i]) - _ORD0) * 10 + (ord(rev[i + 1]) - _ORD0)]
    if n % 2 == 1:
        total += ord(rev[-1]) - _ORD0
    return total % 10


def is_valid_luhn(value: str) -> bool:
    """True si `value` est composé de chiffres et de clé Luhn valide."""
    if not value or not value.isdigit():
        return False
    return luhn_checksum(value) == 0
