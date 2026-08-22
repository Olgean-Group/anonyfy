"""Tests des points fixes de la permutation gazetteer (phase 25, OBJ-REC-110).

Une permutation aleatoire a en moyenne un point fixe; sur un scope dense, un ou
deux noms sortiraient en clair (substitut == clair). Le sondage non-fixe dans
``GazetteerCipher`` garantit qu'aucun nom du gazetteer ne sort en clair.

OBJ-REC-110: le test est INDEPENDANT du contenu du gazetteer -- il parcourt le
gazetteer courant ENTIER (quelle que soit sa taille) sans slice code en dur.
Des tests sur mini-gazetteer avec points fixes connus valident l'algorithme de
sondage (rotation des points fixes, bijection preservee).
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


# --- Mini-gazetteer avec points fixes connus (algorithme de sondage) ---------


class TestSondageMiniGazetteer:
    """Valide l'algorithme de sondage non-fixe sur des mini-gazetteer ou les
    points fixes sont connus (table de permutation predite).

    n=4, key=b'0'*16, scope='s': table=[2, 0, 1, 3], fixed=[3] (1 point fixe).
    n=4, key=b'0'*16, scope='test': table=[0, 3, 2, 1], fixed=[0, 2] (2 points).
    n=3, key=b'0'*16, scope='test': table=[0, 1, 2], fixed=[0,1,2] (identite).
    """

    def test_aucun_point_fixe_1_fixe(self):
        # n=4, scope='s': index 3 est point fixe. Nom trie [0]='aaa', [3]='zzz'.
        g = _mini_gazetteer(["zzz", "aaa", "mmm", "bbb"])
        c = GazetteerCipher(_KEY, "s", "patronyme", g)
        noms = sorted(["zzz", "aaa", "mmm", "bbb"], key=str.casefold)
        for nom in noms:
            sub = c.encrypt(nom)
            assert sub is not None
            assert sub != nom, f"Point fixe: {nom!r} -> {sub!r}"

    def test_aucun_point_fixe_2_fixes(self):
        # n=4, scope='test': index 0 et 2 sont points fixes.
        g = _mini_gazetteer(["zzz", "aaa", "mmm", "bbb"])
        c = GazetteerCipher(_KEY, "test", "patronyme", g)
        noms = sorted(["zzz", "aaa", "mmm", "bbb"], key=str.casefold)
        for nom in noms:
            sub = c.encrypt(nom)
            assert sub is not None
            assert sub != nom, f"Point fixe: {nom!r} -> {sub!r}"

    def test_aucun_point_fixe_identite(self):
        # n=3, scope='test': identite (tous points fixes). Rotation requise.
        g = _mini_gazetteer(["ccc", "aaa", "bbb"])
        c = GazetteerCipher(_KEY, "test", "patronyme", g)
        noms = sorted(["ccc", "aaa", "bbb"], key=str.casefold)
        for nom in noms:
            sub = c.encrypt(nom)
            assert sub is not None
            assert sub != nom, f"Point fixe: {nom!r} -> {sub!r}"

    def test_bijective_apres_sondage(self):
        # Le sondage preserve la bijectivite: N noms -> N substituts distincts.
        g = _mini_gazetteer(["zzz", "aaa", "mmm", "bbb"])
        c = GazetteerCipher(_KEY, "s", "patronyme", g)
        noms = sorted(["zzz", "aaa", "mmm", "bbb"], key=str.casefold)
        subs = [c.encrypt(n) for n in noms]
        assert len(set(subs)) == len(noms)

    def test_round_trip_apres_sondage(self):
        # decrypt(encrypt(nom)) == nom (bijection preservee).
        g = _mini_gazetteer(["zzz", "aaa", "mmm", "bbb"])
        c = GazetteerCipher(_KEY, "s", "patronyme", g)
        noms = sorted(["zzz", "aaa", "mmm", "bbb"], key=str.casefold)
        for nom in noms:
            assert c.decrypt(c.encrypt(nom)) == nom

    def test_round_trip_encrypt_apres_decrypt(self):
        g = _mini_gazetteer(["zzz", "aaa", "mmm", "bbb"])
        c = GazetteerCipher(_KEY, "test", "patronyme", g)
        noms = sorted(["zzz", "aaa", "mmm", "bbb"], key=str.casefold)
        for nom in noms:
            assert c.encrypt(c.decrypt(nom)) == nom


# --- Gazetteer entier (OBJ-REC-110: independant du contenu) -------------------


class TestAucunPointFixeGazetteerEntier:
    """OBJ-REC-110: aucun point fixe sur le gazetteer courant entier.

    Parcourt chaque gazetteer ENTIER (quelle que soit sa taille) et asserter
    qu'aucun nom n'est un point fixe (substitut != clair). Independant du
    contenu: aucune liste de noms codee en dur.
    """

    @pytest.mark.parametrize("etype,loader", _REAL_GAZETTEERS)
    def test_aucun_point_fixe(self, etype, loader):
        gazetteer = loader()
        cipher = GazetteerCipher(_KEY, _SCOPE, etype, gazetteer)
        for entry in gazetteer:
            sub = cipher.encrypt(entry.name)
            assert sub is not None, f"{entry.name!r}: substitut None"
            assert sub != entry.name, f"Point fixe {etype}: {entry.name!r} -> {sub!r}"

    @pytest.mark.parametrize("etype,loader", _REAL_GAZETTEERS)
    def test_aucun_point_fixe_casefold(self, etype, loader):
        """Le clair en casse variante (UPPER) ne doit pas etre point fixe."""
        gazetteer = loader()
        cipher = GazetteerCipher(_KEY, _SCOPE, etype, gazetteer)
        for entry in gazetteer:
            sub = cipher.encrypt(entry.name.upper())
            assert sub is not None
            assert sub.casefold() != entry.name.casefold(), (
                f"Point fixe (casefold) {etype}: {entry.name!r} -> {sub!r}"
            )


class TestDeterminisme:
    """Meme (scope, type, clair, cle) -> meme substitut non-fixe."""

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
    """Le sondage non-fixe preserve la bijectivite (N noms -> N substituts)."""

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
