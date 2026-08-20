"""Algorithme de Luhn (phase 05).

Somme de contrôle de Luhn utilisée par SIREN, SIRET et carte bancaire.
L'algorithme: de droite à gauche, on double un chiffre sur deux (en partant du
second chiffre); si le doublement dépasse 9, on soustrait 9; la somme modulo 10
doit valoir 0.

Référence: PLAN.md phase 05, PRD §7 (SIREN/SIRET/carte bancaire).
"""

from __future__ import annotations

__all__ = ["is_valid_luhn", "luhn_checksum"]


def luhn_checksum(digits: str) -> int:
    """Renvoie la somme de contrôle de Luhn modulo 10 d'une chaîne de chiffres.

    Lève ValueError si la chaîne contient autre chose que des chiffres ou est vide.
    """
    if not digits or not digits.isdigit():
        raise ValueError(f"chaîne non numérique ou vide: {digits!r}")
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10


def is_valid_luhn(value: str) -> bool:
    """True si `value` est composé de chiffres et de clé Luhn valide."""
    if not value or not value.isdigit():
        return False
    return luhn_checksum(value) == 0
