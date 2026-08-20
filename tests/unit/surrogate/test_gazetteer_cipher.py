"""Tests du cipher gazetteer par permutation (D22, types non-FPE).

Patronyme/prenom/commune/voie: permutation sur l'index canonique du gazetteer.
Nom inconnu -> non masqué (None). Round-trip sur noms connus.
"""

import pytest

from anonyfy.detect.gazetteers.loader import Gazetteer, GazetteerEntry
from anonyfy.surrogate.gazetteer_cipher import GazetteerCipher

_KEY = b"secret-key-32-bytes-padding-ok!!!"


def _mini_gazetteer(noms: list[str]) -> Gazetteer:
    entries = {n.casefold(): GazetteerEntry(name=n) for n in noms}
    return Gazetteer(entries)


class TestEncryptDecrypt:
    """Round-trip sur noms connus du gazetteer."""

    def test_encrypt_retourne_nom_du_gazetteer(self):
        g = _mini_gazetteer(["Martin", "Dupont", "Bernard", "Petit", "Durand"])
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        sub = c.encrypt("Martin")
        assert sub is not None
        assert sub in [e.name for e in g]

    def test_round_trip_decrypt_apres_encrypt(self):
        g = _mini_gazetteer(["Martin", "Dupont", "Bernard", "Petit", "Durand"])
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        for nom in ["Martin", "Dupont", "Bernard", "Petit", "Durand"]:
            assert c.decrypt(c.encrypt(nom)) == nom

    def test_round_trip_encrypt_apres_decrypt(self):
        g = _mini_gazetteer(["Martin", "Dupont", "Bernard", "Petit", "Durand"])
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        for nom in ["Martin", "Dupont", "Bernard", "Petit", "Durand"]:
            assert c.encrypt(c.decrypt(nom)) == nom

    def test_encrypt_differe_de_clair(self):
        # Le substitut doit différer du clair (sinon fuite)
        g = _mini_gazetteer(["Martin", "Dupont", "Bernard", "Petit", "Durand"])
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        for nom in ["Martin", "Dupont", "Bernard", "Petit", "Durand"]:
            assert c.encrypt(nom) != nom


class TestNomInconnu:
    """Nom inconnu du gazetteer -> non masqué (None), choix (ii) D22."""

    def test_nom_inconnu_retourne_none(self):
        g = _mini_gazetteer(["Martin", "Dupont"])
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        assert c.encrypt("Lefevre") is None

    def test_decrypt_nom_inconnu_retourne_none(self):
        g = _mini_gazetteer(["Martin", "Dupont"])
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        assert c.decrypt("Lefevre") is None


class TestBijectivite:
    """N patronymes distincts -> N substituts distincts (pas de collision)."""

    def test_bijectif_sur_mini_gazetteer(self):
        noms = [f"Nom{i}" for i in range(100)]
        g = _mini_gazetteer(noms)
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        subs = [c.encrypt(n) for n in noms]
        assert len(set(subs)) == len(noms)

    def test_bijectif_grand(self):
        # 5000 patronymes distincts (critère 4 no-collision)
        noms = [f"Patronyme{i:05d}" for i in range(5000)]
        g = _mini_gazetteer(noms)
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        subs = [c.encrypt(n) for n in noms]
        assert len(set(subs)) == len(noms)


class TestScopeEtCle:
    """Scope/clé distincts -> permutations distinctes."""

    def test_scope_distinct_differe(self):
        g = _mini_gazetteer(["Martin", "Dupont", "Bernard", "Petit", "Durand"])
        ca = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        cb = GazetteerCipher(_KEY, "scope-b", "patronyme", g)
        diffs = [n for n in [e.name for e in g] if ca.encrypt(n) != cb.encrypt(n)]
        assert len(diffs) > 0

    def test_cle_distincte_differe(self):
        g = _mini_gazetteer(["Martin", "Dupont", "Bernard", "Petit", "Durand"])
        ca = GazetteerCipher(b"key-aaaaaaaaaaaaaaaaaaaaaaaaaa!", "scope-a", "patronyme", g)
        cb = GazetteerCipher(b"key-bbbbbbbbbbbbbbbbbbbbbbbbbbb!", "scope-a", "patronyme", g)
        diffs = [n for n in [e.name for e in g] if ca.encrypt(n) != cb.encrypt(n)]
        assert len(diffs) > 0


class TestDeterminisme:
    """encrypt(nom)==encrypt(nom) mêmes args."""

    def test_deterministe(self):
        g = _mini_gazetteer(["Martin", "Dupont", "Bernard"])
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        for _ in range(3):
            assert c.encrypt("Martin") == c.encrypt("Martin")


class TestCasefold:
    """Lookup insensible à la casse."""

    def test_encrypt_casefold(self):
        g = _mini_gazetteer(["Martin"])
        c = GazetteerCipher(_KEY, "scope-a", "patronyme", g)
        assert c.encrypt("MARTIN") == c.encrypt("martin")
        assert c.decrypt(c.encrypt("MARTIN")) == "Martin"