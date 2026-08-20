"""Dictionnaire de variantes normalisées des substituts (phase 10b).

Génère les variantes **bornées** d'un substitut (surrogate) pour que l'automate
Aho-Corasick (``aho_corasick.py``) retrouve un substitut dans la réponse d'un
modèle même reformatée.

**Invariant 1 (architecture §6)**: les variantes s'appliquent au **substitut**,
pas au clair. L'automate cherche les substituts, jamais le clair.

Classes de variantes couvertes (bornées, PLAN phase 10b):
- **groupes de chiffres**: un substitut numérique ``41804261100034`` est aussi
  cherché sous la forme groupée par 3 ``418 042 611 000 34``.
- **casses**: minuscules / majuscules (``Pierre Dupont`` -> ``pierre dupont``,
  ``PIERRE DUPONT``).
- **espaces**: collapsage des espaces multiples et suppression des espaces.
- **ponctuation**: formes avec / sans point du préfixe « M. »
  (``M. Dupont`` / ``M Dupont`` / ``M.Dupont``).
- **« M. <nom> »**: un substitut patronyme ``Pierre Dupont`` est aussi cherché
  sous ``M. Dupont`` quand le prénom est substitué séparément (dernier token =
  nom).

Les variantes exotiques ne sont pas couvertes (documenté comme limite dans le
PLAN, risque d'explosion combinatoire).

Référence: PLAN.md phase 10b, D7/OBJ-005, architecture §6, invariant 1.
"""

from __future__ import annotations

import re

__all__ = ["expand"]

# Seuil de longueur pour le regroupement par 3: évite de produire une variante
# identique au substitut pour les chaînes trop courtes (<= 2 chiffres).
_MIN_DIGIT_GROUPING_LEN = 3
_GROUP_SIZE = 3


def expand(substitute: str) -> list[str]:
    """Renvoie le substitut et ses variantes normalisées bornées.

    Le substitut lui-même est toujours le premier élément de la liste. Les
    variantes sont dédupliquées et ordonnées par ordre d'ajout. Aucune variante
    vide n'est renvoyée. Renvoie ``[]`` pour un substitut vide.

    Les variantes s'appliquent au **substitut** (pas au clair, invariant 1).
    """
    if not substitute:
        return []

    result: list[str] = []
    seen: set[str] = set()

    def add(variant: str) -> None:
        if variant and variant not in seen:
            seen.add(variant)
            result.append(variant)

    add(substitute)
    for v in _case_variants(substitute):
        add(v)
    for v in _digit_grouping(substitute):
        add(v)
    for v in _monsieur_variant(substitute):
        add(v)
    for v in _space_punct_variants(substitute):
        add(v)

    return result


def _case_variants(substitute: str) -> list[str]:
    """Variantes de casse: minuscules et majuscules.

    Pour un substitut purement numérique, les casses sont identiques au substitut
    et seront dédupliquées par ``expand``.
    """
    return [substitute.lower(), substitute.upper()]


def _digit_grouping(substitute: str) -> list[str]:
    """Variante de regroupement des chiffres par 3 (espacé).

    Un substitut numérique ``41804261100034`` devient ``418 042 611 000 34``.
    Ne s'applique qu'aux substituts purement numériques d'au moins 3 chiffres;
    ne produit pas de variante si le regroupement est identique au substitut.
    """
    if not substitute.isdigit() or len(substitute) < _MIN_DIGIT_GROUPING_LEN:
        return []
    grouped = " ".join(
        substitute[i : i + _GROUP_SIZE] for i in range(0, len(substitute), _GROUP_SIZE)
    )
    if grouped == substitute:
        return []
    return [grouped]


def _monsieur_variant(substitute: str) -> list[str]:
    """Variantes « M. <nom> » / « M <nom> » / « M.<nom> ».

    Quand le prénom est substitué séparément, un substitut patronyme
    ``Pierre Dupont`` peut apparaître sous la forme ``M. Dupont`` (dernier token
    = nom). On génère les trois formes de ponctuation du préfixe « M ».

    Ne s'applique qu'aux substituts à plusieurs tokens (au moins un prénom + nom).
    """
    parts = substitute.split()
    if len(parts) < 2:
        return []
    last = parts[-1]
    return [f"M. {last}", f"M {last}", f"M.{last}"]


def _space_punct_variants(substitute: str) -> list[str]:
    """Variantes d'espaces: collapsage des espaces multiples et suppression.

    ``Pierre  Dupont`` -> ``Pierre Dupont`` (collapsé) ; ``Pierre Dupont`` ->
    ``PierreDupont`` (sans espace). N'inclut pas une variante identique au
    substitut.
    """
    collapsed = re.sub(r"\s+", " ", substitute).strip()
    no_space = re.sub(r"\s+", "", substitute)
    out: list[str] = []
    if collapsed != substitute:
        out.append(collapsed)
    if no_space != substitute:
        out.append(no_space)
    return out
