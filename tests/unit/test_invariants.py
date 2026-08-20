"""Tests de formalisation des 4 invariants (architecture.md §1).

Logique testee: chaque invariant est represente par une exception dediee
et une fonction de verification pure qui leve sur contrexemple construit.
Aucune logique de masquage ici: on verifie des proprietes sur des donnees
fournies.
"""

from __future__ import annotations

import pytest

from anonyfy.invariants import (
    ClearBoundaryViolation,
    InjectivityViolation,
    InvariantViolation,
    ScopedDeterminismViolation,
    UnmaskWithoutMaskViolation,
    assert_injectivity,
    assert_no_clear_leak,
    assert_only_emitted_unmasked,
    assert_scoped_determinism,
)


class TestHierarchieExceptions:
    def test_quatre_exceptions_sous_base(self):
        for exc in (
            ClearBoundaryViolation,
            ScopedDeterminismViolation,
            InjectivityViolation,
            UnmaskWithoutMaskViolation,
        ):
            assert issubclass(exc, InvariantViolation), (
                f"{exc.__name__} pas sous InvariantViolation"
            )

    def test_exceptions_distinctes(self):
        excs = {
            ClearBoundaryViolation,
            ScopedDeterminismViolation,
            InjectivityViolation,
            UnmaskWithoutMaskViolation,
        }
        assert len(excs) == 4


class TestInvariant1ClairFrontiere:
    """Invariant 1: le clair ne franchit jamais la frontiere."""

    def test_pas_de_fuite_ne_leve_pas(self):
        # Aucun token clair present dans le masque -> OK.
        assert_no_clear_leak(["Jean", "Dupont", "73282932000035"], "Marc Leroy 41804261100034")

    def test_fuite_leve_clear_boundary(self):
        # Un token clair present dans le masque -> violation.
        with pytest.raises(ClearBoundaryViolation):
            assert_no_clear_leak(["Jean"], "Bonjour Jean ici")

    def test_fuite_substitut_complet(self):
        with pytest.raises(ClearBoundaryViolation):
            assert_no_clear_leak(["73282932000035"], "SIRET 73282932000035")

    def test_token_vide_ignore(self):
        # Un token vide n'est pas une fuite significative (evite faux positif).
        assert_no_clear_leak([""], "n'importe quoi")

    def test_aucun_token_ne_leve_pas(self):
        assert_no_clear_leak([], "n'importe quoi")


class TestInvariant2DeterminismeScope:
    """Invariant 2: dans un scope, une valeur produit toujours le meme substitut."""

    def test_substituts_constants_ne_leve_pas(self):
        assert_scoped_determinism(["X", "X", "X"])
        assert_scoped_determinism(["X"])

    def test_substituts_variables_leve(self):
        with pytest.raises(ScopedDeterminismViolation):
            assert_scoped_determinism(["X", "Y", "X"])

    def test_sequence_vide_ne_leve_pas(self):
        assert_scoped_determinism([])


class TestInvariant3Injectivite:
    """Invariant 3: deux valeurs distinctes ne partagent jamais un substitut."""

    def test_injectif_ne_leve_pas(self):
        assert_injectivity({"a": "X", "b": "Y", "c": "Z"})

    def test_collision_leve(self):
        with pytest.raises(InjectivityViolation):
            assert_injectivity({"a": "X", "b": "X"})

    def test_cle_unique_meme_substitut_ok(self):
        # Une entree unique -> un substitut, ce n'est pas une collision
        # (le determinisme est suppose; l'injectivite porte sur les cles distinctes).
        assert_injectivity({"a": "X"})

    def test_mapping_vide_ne_leve_pas(self):
        assert_injectivity({})


class TestInvariant4RienDemasqueNonMasque:
    """Invariant 4: unmask ne transforme que des substituts reellement emis."""

    def test_substitut_emis_ne_leve_pas(self):
        assert_only_emitted_unmasked("X", {"X", "Y"})

    def test_substitut_non_emis_leve(self):
        # Un identifiant invente par le modele, jamais emis, ne doit pas etre
        # demasque. Le verifier doit lever.
        with pytest.raises(UnmaskWithoutMaskViolation):
            assert_only_emitted_unmasked("INVENTE", {"X", "Y"})

    def test_ensemble_vide_substitut_leve(self):
        with pytest.raises(UnmaskWithoutMaskViolation):
            assert_only_emitted_unmasked("X", set())


class TestContreExemplesConstruits:
    """Risque documente: un test par invariant echoue sur un contrexemple construit."""

    def test_contrexemple_invariant1(self):
        # Si "Dupont" (clair) apparait dans le masque, c'est une fuite.
        with pytest.raises(ClearBoundaryViolation):
            assert_no_clear_leak(["Dupont"], "M. Dupont demeurant...")

    def test_contrexemple_invariant2(self):
        # Si mask("x") produit "A" puis "B" dans le meme scope, determinisme rompu.
        with pytest.raises(ScopedDeterminismViolation):
            assert_scoped_determinism(["A", "B"])

    def test_contrexemple_invariant3(self):
        # Si deux valeurs claires distinctes -> meme substitut, unmask est ambigu.
        with pytest.raises(InjectivityViolation):
            assert_injectivity({"Jean": "Marc Leroy", "Pierre": "Marc Leroy"})

    def test_contrexemple_invariant4(self):
        # Si unmask decode un SIRET valide jamais emis, il produit une fausse claire.
        with pytest.raises(UnmaskWithoutMaskViolation):
            assert_only_emitted_unmasked("41804261100034", {"73282932000035"})
