"""Tests de la permutation gazetteer (phase 25, OBJ-REC-110).

Phase 35 (D35b): le dérangement est supprimé. Les points fixes (~1 par
gazetteer) réapparaissent et sont traités par le filet de sûreté global
(D35f) dans ``Engine.mask``; la non-fuite est mesurée dans
``tests/acceptance/test_no_leak_composite.py`` (pas de test orphelin).

Ce fichier conserve les invariants indépendants du dérangement:
déterminisme (même scope/type/clair/clé -> même substitut) et bijectivité
(N noms -> N substituts distincts, round-trip exact).
"""

from __future__ import annotations

import pytest

from anonyfy.detect.gazetteers.loader import (
    Gazetteer,
    GazetteerEntry,
    load_communes,
    load_noms,
    load_prenoms,
    load_voies,
)
from anonyfy.surrogate.gazetteer_cipher import GazetteerCipher

_KEY = b"0" * 16
_SCOPE = "s"

# Les 4 types gazetteer (D22): patronyme, prenom, commune, voie.
_REAL_GAZETTEERS = [
    ("patronyme", load_noms),
    ("prenom", load_prenoms),
    ("commune", load_communes),
    ("voie", load_voies),
]


def _mini_gazetteer(noms: list[str]) -> Gazetteer:
    entries = {n.casefold(): GazetteerEntry(name=n) for n in noms}
    return Gazetteer(entries)


class TestDeterminisme:
    """Meme (scope, type, clair, cle) -> meme substitut."""

    @pytest.mark.parametrize("etype,loader", _REAL_GAZETTEERS)
    def test_determinisme_meme_appel(self, etype, loader):
        gazetteer = loader()
        cipher = GazetteerCipher(_KEY, _SCOPE, etype, gazetteer)
        for entry in list(gazetteer)[:50]:
            assert cipher.encrypt(entry.name) == cipher.encrypt(entry.name)

    @pytest.mark.parametrize("etype,loader", _REAL_GAZETTEERS)
    def test_determinisme_meme_cle_scope(self, etype, loader):
        gazetteer = loader()
        c1 = GazetteerCipher(_KEY, _SCOPE, etype, gazetteer)
        c2 = GazetteerCipher(_KEY, _SCOPE, etype, gazetteer)
        for entry in list(gazetteer)[:50]:
            assert c1.encrypt(entry.name) == c2.encrypt(entry.name)


class TestBijectivitePreservee:
    """Bijectivite (N noms -> N substituts) et round-trip exact."""

    @pytest.mark.parametrize("etype,loader", _REAL_GAZETTEERS)
    def test_bijectif_sur_gazetteer_entier(self, etype, loader):
        gazetteer = loader()
        cipher = GazetteerCipher(_KEY, _SCOPE, etype, gazetteer)
        noms = [e.name for e in gazetteer]
        subs = [cipher.encrypt(n) for n in noms]
        assert len(set(subs)) == len(noms)

    @pytest.mark.parametrize("etype,loader", _REAL_GAZETTEERS)
    def test_round_trip_sur_gazetteer(self, etype, loader):
        gazetteer = loader()
        cipher = GazetteerCipher(_KEY, _SCOPE, etype, gazetteer)
        for entry in list(gazetteer)[:200]:
            assert cipher.decrypt(cipher.encrypt(entry.name)) == entry.name
