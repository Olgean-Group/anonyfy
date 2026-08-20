"""Tests de la permutation keyée Feistel (primitive D22).

Cycle-walking pour n non puissance de 2. Bijective sur [0, n). Inversible.
Déterminisme scopé (key+scope+entity_type). Stdlib uniquement.
"""

import pytest

from anonyfy.surrogate.permutation import Permutation

_KEY = b"secret-key-32-bytes-padding-ok!!!"


def _perm(scope: str, entity_type: str, n: int, key: bytes = _KEY) -> Permutation:
    return Permutation(key=key, scope=scope, entity_type=entity_type, n=n)


class TestBijectiviteExhaustive:
    """Bijectivité exhaustive sur petits n."""

    def test_n10_bijectif(self):
        p = _perm("scope-a", "patronyme", 10)
        images = [p.encrypt(x) for x in range(10)]
        assert set(images) == set(range(10))

    def test_n100_bijectif(self):
        p = _perm("scope-a", "patronyme", 100)
        images = [p.encrypt(x) for x in range(100)]
        assert set(images) == set(range(100))

    def test_n1000_bijectif(self):
        p = _perm("scope-a", "patronyme", 1000)
        images = [p.encrypt(x) for x in range(1000)]
        assert set(images) == set(range(1000))


class TestInversibilite:
    """decrypt(encrypt(x))==x et encrypt(decrypt(y))==y."""

    def test_round_trip_decrypt_apres_encrypt(self):
        p = _perm("scope-a", "patronyme", 1000)
        for x in range(1000):
            assert p.decrypt(p.encrypt(x)) == x

    def test_round_trip_encrypt_apres_decrypt(self):
        p = _perm("scope-a", "patronyme", 1000)
        for y in range(1000):
            assert p.encrypt(p.decrypt(y)) == y

    def test_round_trip_n100(self):
        p = _perm("scope-a", "commune", 100)
        for x in range(100):
            assert p.decrypt(p.encrypt(x)) == x


class TestDeterminisme:
    """encrypt(x)==encrypt(x) mêmes args."""

    def test_encrypt_deterministe(self):
        p = _perm("scope-a", "patronyme", 1000)
        for x in (0, 1, 42, 999):
            assert p.encrypt(x) == p.encrypt(x)

    def test_decrypt_deterministe(self):
        p = _perm("scope-a", "patronyme", 1000)
        for y in (0, 1, 42, 999):
            assert p.decrypt(y) == p.decrypt(y)


class TestScopeDistinct:
    """Scopes distincts donnent permutations distinctes."""

    def test_scope_a_vs_b_differe(self):
        pa = _perm("scope-a", "patronyme", 1000)
        pb = _perm("scope-b", "patronyme", 1000)
        diffs = [x for x in range(1000) if pa.encrypt(x) != pb.encrypt(x)]
        assert len(diffs) > 0

    def test_type_distinct_differe(self):
        pa = _perm("scope-a", "patronyme", 1000)
        pb = _perm("scope-a", "commune", 1000)
        diffs = [x for x in range(1000) if pa.encrypt(x) != pb.encrypt(x)]
        assert len(diffs) > 0


class TestCleDistincte:
    """Clés distinctes donnent permutations distinctes."""

    def test_cle_a_vs_b_differe(self):
        pa = _perm("scope-a", "patronyme", 1000, key=b"key-aaaaaaaaaaaaaaaaaaaaaaaaaa!")
        pb = _perm("scope-a", "patronyme", 1000, key=b"key-bbbbbbbbbbbbbbbbbbbbbbbbbbb!")
        diffs = [x for x in range(1000) if pa.encrypt(x) != pb.encrypt(x)]
        assert len(diffs) > 0


class TestCycleWalking:
    """n non puissance de 2: cycle-walking préserve bijectivité."""

    def test_n1000_cycle_walking_bijectif(self):
        # 1000 < 1024 = 2^10, domaine non puissance de 2
        p = _perm("scope-a", "patronyme", 1000)
        images = [p.encrypt(x) for x in range(1000)]
        assert set(images) == set(range(1000))

    def test_n999_cycle_walking_bijectif(self):
        p = _perm("scope-a", "patronyme", 999)
        images = [p.encrypt(x) for x in range(999)]
        assert set(images) == set(range(999))

    def test_n1023_cycle_walking_bijectif(self):
        # 1023 = 2^10 - 1, pire cas cycle-walking
        p = _perm("scope-a", "patronyme", 1023)
        images = [p.encrypt(x) for x in range(1023)]
        assert set(images) == set(range(1023))

    def test_n1000_inversible_apres_cycle_walking(self):
        p = _perm("scope-a", "patronyme", 1000)
        for x in (0, 500, 999):
            assert p.decrypt(p.encrypt(x)) == x


class TestEdgeCases:
    """Cas limites."""

    def test_n1_trivial(self):
        p = _perm("scope-a", "patronyme", 1)
        assert p.encrypt(0) == 0
        assert p.decrypt(0) == 0

    def test_n2_bijectif(self):
        p = _perm("scope-a", "patronyme", 2)
        images = [p.encrypt(x) for x in range(2)]
        assert set(images) == set(range(2))

    def test_rejette_x_negatif(self):
        p = _perm("scope-a", "patronyme", 100)
        with pytest.raises(ValueError):
            p.encrypt(-1)

    def test_rejette_x_hors_domaine(self):
        p = _perm("scope-a", "patronyme", 100)
        with pytest.raises(ValueError):
            p.encrypt(100)

    def test_rejette_decrypt_hors_domaine(self):
        p = _perm("scope-a", "patronyme", 100)
        with pytest.raises(ValueError):
            p.decrypt(100)

    def test_rejette_decrypt_negatif(self):
        p = _perm("scope-a", "patronyme", 100)
        with pytest.raises(ValueError):
            p.decrypt(-1)
