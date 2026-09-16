"""Formalisation des 4 invariants d'anonyfy (architecture.md §1).

Ce module definit les exceptions dediees a chaque violation et des fonctions
de verification *pures*: elles operent sur des donnees fournies et levent si la
propriete est rompue. Aucune logique de masquage/detection/registre n'est
implementee ici (FPE = phase 07, registre = phase 10); les verificateurs
servent de contrats testables pour les phases ulterieures.

Les 4 invariants:
  1. Le clair ne franchit jamais la frontiere.
  2. Determinisme scope: une valeur -> toujours le meme substitut dans un scope.
  3. Injectivite dans le scope: deux valeurs distinctes -> deux substituts distincts.
  4. Rien n'est demasque qui n'ait ete masque.
"""

from __future__ import annotations

from collections.abc import Container, Mapping, Sequence


class InvariantViolation(Exception):
    """Base des violations d'invariants anonyfy."""


class ClearBoundaryViolation(InvariantViolation):
    """Invariant 1: une valeur claire a franchi la frontiere (fuite dans le masque)."""


class ScopedDeterminismViolation(InvariantViolation):
    """Invariant 2: une meme valeur a produit des substituts differents dans un scope."""


class InjectivityViolation(InvariantViolation):
    """Invariant 3: deux valeurs claires distinctes partagent un meme substitut."""


class UnmaskWithoutMaskViolation(InvariantViolation):
    """Invariant 4: un substitut non emis dans le scope a ete demasque."""


class SameTypeViolation(InvariantViolation):
    """F3-type: un substitut n'est pas du meme type que le clair (repli silencieux)."""


def assert_no_clear_leak(clear_tokens: Sequence[str], masked: str) -> None:
    """Invariant 1: aucun token clair ne doit apparaitre dans le texte masque.

    Leve ClearBoundaryViolation si l'un des tokens clairs (non vides) est
    present comme sous-chaine dans `masked`. Les tokens vides sont ignores
    (un token vide est trivialement present partout).
    """
    for token in clear_tokens:
        if token and token in masked:
            raise ClearBoundaryViolation(f"token clair presente dans le masque: {token!r}")


def assert_scoped_determinism(substitutes: Sequence[str]) -> None:
    """Invariant 2: une meme valeur produit toujours le meme substitut dans un scope.

    `substitutes` est la sequence des substituts obtenus pour une meme
    (scope, valeur) lors d'appels repetes. Leve ScopedDeterminismViolation
    s'ils ne sont pas tous egaux.
    """
    uniques = set(substitutes)
    if len(uniques) > 1:
        raise ScopedDeterminismViolation(
            f"plusieurs substituts pour une meme valeur: {sorted(uniques)!r}"
        )


def assert_injectivity(mapping: Mapping[str, str]) -> None:
    """Invariant 3: deux valeurs claires distinctes ne partagent pas un substitut.

    Leve InjectivityViolation si deux cles distinctes de `mapping` pointent
    vers la meme valeur de substitut. Deux entrees de cle identique avec le
    meme substitut n'est pas une violation (c'est le determinisme).
    """
    attribue_a: dict[str, str] = {}
    for clear, sub in mapping.items():
        if sub in attribue_a and attribue_a[sub] != clear:
            raise InjectivityViolation(
                f"substitut {sub!r} attribue a {clear!r} et {attribue_a[sub]!r}"
            )
        attribue_a[sub] = clear


def assert_only_emitted_unmasked(substitute: str, emitted: Container[str]) -> None:
    """Invariant 4: un substitut demasque doit avoir ete emis dans le scope.

    Leve UnmaskWithoutMaskViolation si `substitute` n'appartient pas a
    `emitted` (l'ensemble des substituts reellement emis dans le scope).
    Un identifiant invente par le modele ne doit jamais etre decode en une
    fausse valeur claire.
    """
    if substitute not in emitted:
        raise UnmaskWithoutMaskViolation(f"substitut non emis dans le scope: {substitute!r}")


def assert_substitute_same_type(
    span: object,
    expected_type: object,
) -> None:
    """F3-type: le substitut d'un span est de meme type que le clair attendu.

    Phase 52 (REV-MIN-1): formalisation de l'invariant declare au PRD
    (« substitut de meme type »). Un span dont le type differe du type attendu,
    ou dont la regle de masquage designe un autre type (``mask-<type>``), est
    un repli silencieux: il leve ``SameTypeViolation``.

    Args:
        span: objet portant ``type`` et ``rule_id`` (``anonyfy.types.Span``).
        expected_type: type attendu pour ce token.

    Les regles de detection (avant masquage, ex. ``gazetteer-commune``) sont
    acceptees: seul le type est alors verifie. Une regle ``mask-*`` doit
    designer le type declare.
    """
    declared = getattr(span, "type", None)
    rule_id = getattr(span, "rule_id", "")
    if declared != expected_type:
        raise SameTypeViolation(
            f"substitut de type {getattr(declared, 'value', declared)!r} "
            f"pour un clair attendu {getattr(expected_type, 'value', expected_type)!r}"
        )
    if isinstance(rule_id, str) and rule_id.startswith("mask-"):
        expected_rule = f"mask-{getattr(declared, 'value', declared).lower()}"
        if rule_id != expected_rule:
            raise SameTypeViolation(
                f"regle de masquage {rule_id!r} incoherente avec le type declare "
                f"({expected_rule!r} attendu)"
            )


__all__ = [
    "ClearBoundaryViolation",
    "InjectivityViolation",
    "InvariantViolation",
    "SameTypeViolation",
    "ScopedDeterminismViolation",
    "UnmaskWithoutMaskViolation",
    "assert_injectivity",
    "assert_no_clear_leak",
    "assert_only_emitted_unmasked",
    "assert_scoped_determinism",
    "assert_substitute_same_type",
]
