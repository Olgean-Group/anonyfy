"""Recalcul des clés de contrôle pour les substituts FPE (phase 07).

FPE préserve la longueur mais pas la validité de la clé de contrôle. Après
chiffrement du corps significatif, on recalcule la clé (Luhn, mod 97 NIR,
mod 97 IBAN, clé TVA) pour que le substitut soit **valide au format** de
l'original. Sans ce recalcul, un SIRET chiffré ne passerait plus le Luhn et le
modèle de langage perdrait le raisonnement sur la valeur (PRD F3, ADR 0001 §2).

Référence: PLAN.md phase 07, ADR 0001 §2 (recalcul des clés).
"""

from __future__ import annotations

from anonyfy.detect.validators.mod97 import iban_mod97, nir_control_key

__all__ = ["iban_check_digits", "luhn_check_digit", "nir_key", "tva_key"]


def luhn_check_digit(body: str) -> int:
    """Renvoie le chiffre de contrôle de Luhn à appendre à `body` pour que la
    chaîne complète soit Luhn-valide.

    Lève ValueError si `body` n'est pas composé de chiffres ou est vide.
    """
    if not body or not body.isdigit():
        raise ValueError(f"corps non numérique ou vide: {body!r}")
    for c in range(10):
        total = 0
        candidate = body + str(c)
        for i, ch in enumerate(reversed(candidate)):
            n = int(ch)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        if total % 10 == 0:
            return c
    # Mathématiquement inaccessible (10 chiffres testés sur un modulo 10).
    raise RuntimeError("aucune clé de Luhn trouvée")


def nir_key(base13: str) -> str:
    """Renvoie la clé NIR (2 chiffres) du préfixe à 13 caractères significatifs.

    La clé est le complément à 97 du reste mod 97 des 13 chiffres (avec la
    substitution Corse 2A→19, 2B→18). Gérée par `mod97.nir_control_key`.

    Lève ValueError si `base13` n'est pas un préfixe NIR convertible.
    """
    return f"{nir_control_key(base13):02d}"


def iban_check_digits(bban: str, country: str = "FR") -> str:
    """Renvoie les 2 chiffres de clé IBAN pour un BBAN et un code pays donnés.

    La clé IBAN est l'unique valeur `c` (00..97) telle que
    `mod97(country + c + bban) == 1`. Pour la France, le BBAN fait 23 chiffres.

    Lève ValueError si `bban` n'est pas numérique ou de longueur incohérente.
    """
    if not bban or not bban.isdigit():
        raise ValueError(f"BBAN non numérique ou vide: {bban!r}")
    if country != "FR":
        raise ValueError(f"pays non supporté en phase 07: {country!r}")
    if len(bban) != 23:
        raise ValueError(f"BBAN FR attendu à 23 chiffres, reçu {len(bban)}")
    for c in range(98):
        candidate = f"{country}{c:02d}{bban}"
        if iban_mod97(candidate) == 1:
            return f"{c:02d}"
    # c ∈ [0, 97] couvre tous les restes mod 97; inaccessible.
    raise RuntimeError("aucune clé IBAN trouvée")


def tva_key(siren9: str) -> str:
    """Renvoie la clé TVA intracommunautaire FR (2 chiffres) pour un SIREN.

    Clé = (12 + 3 * (SIREN mod 97)) mod 97. Lève ValueError si `siren9` n'est pas
    numérique.
    """
    if not siren9 or not siren9.isdigit():
        raise ValueError(f"SIREN non numérique ou vide: {siren9!r}")
    key = (12 + 3 * (int(siren9) % 97)) % 97
    return f"{key:02d}"
