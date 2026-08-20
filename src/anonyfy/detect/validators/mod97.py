"""Helpers mod 97 pour IBAN et NIR (phase 05).

IBAN: on déplace les 4 premiers caractères (pays + clé) en fin de chaîne, on
convertit les lettres (A=10 ... Z=35), et le reste modulo 97 doit valoir 1.

NIR: la clé de contrôle est le complément à 97 du reste des 13 chiffres
significatifs modulo 97. La Corse utilise les codes départementaux 2A et 2B;
pour le calcul on substitue 2A -> 19 et 2B -> 18.

Référence: PLAN.md phase 05, PRD §7 (IBAN, NIR).
"""

from __future__ import annotations

__all__ = ["iban_mod97", "mod97_remainder", "nir_control_key"]


def mod97_remainder(number_str: str) -> int:
    """Reste de la division par 97 d'un grand entier donné sous forme de chaîne."""
    if not number_str or not number_str.isdigit():
        raise ValueError(f"chaîne non numérique ou vide: {number_str!r}")
    return int(number_str) % 97


def iban_mod97(iban: str) -> int:
    """Reste modulo 97 d'un IBAN (réarrangé + lettres converties en chiffres)."""
    if len(iban) < 5:
        raise ValueError(f"IBAN trop court: {iban!r}")
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(
        str(ord(c) - ord("A") + 10) if c.isalpha() else c for c in rearranged
    )
    return int(numeric) % 97


def nir_control_key(nir13: str) -> int:
    """Clé de contrôle NIR (complément à 97) d'un préfixe à 13 caractères.

    Gestion Corse: 2A est substitué par 19, 2B par 18 avant la division.
    """
    if len(nir13) != 13:
        raise ValueError(f"préfixe NIR attendu à 13 caractères: {nir13!r}")
    digits = nir13.replace("2A", "19").replace("2B", "18")
    if not digits.isdigit():
        raise ValueError(f"préfixe NIR non convertible en nombre: {nir13!r}")
    return 97 - (int(digits) % 97)