"""Tests du cipher plaque SIV par permutation (D2, D22).

3 chiffres -> permutation sur [0, 1000). Lettres preservées.
Substitut format-valide LL-DDD-LL[L]. Round-trip reversible.
"""

from anonyfy.detect.validators.plate import validate
from anonyfy.surrogate.plate_cipher import PlateCipher

_KEY = b"secret-key-32-bytes-padding-ok!!!"


class TestFormatValide:
    """Le substitut est une plaque SIV format-valide."""

    def test_encrypt_format_valide(self):
        c = PlateCipher(_KEY, "scope-a")
        sub = c.encrypt("AB-123-CD")
        assert sub is not None
        assert validate(sub)

    def test_encrypt_preserve_lettres(self):
        c = PlateCipher(_KEY, "scope-a")
        sub = c.encrypt("AB-123-CD")
        assert sub.startswith("AB-")
        assert sub.endswith("-CD")

    def test_encrypt_preserve_lettres_3(self):
        c = PlateCipher(_KEY, "scope-a")
        sub = c.encrypt("AB-123-CDE")
        assert sub.startswith("AB-")
        assert sub.endswith("-CDE")


class TestRoundTrip:
    """decrypt(encrypt(x))==x."""

    def test_round_trip(self):
        c = PlateCipher(_KEY, "scope-a")
        plaques = ["AB-123-CD", "GH-456-EF", "DK-789-LMN", "AB-000-CD", "ZZ-999-ZZ"]
        for p in plaques:
            assert c.decrypt(c.encrypt(p)) == p

    def test_round_trip_encrypt_apres_decrypt(self):
        c = PlateCipher(_KEY, "scope-a")
        for p in ["AB-123-CD", "GH-456-EF"]:
            assert c.encrypt(c.decrypt(p)) == p


class TestPermutationChiffres:
    """Les 3 chiffres sont permutes (sur un echantillon, la plupart different)."""

    def test_chiffres_permutes_majorite(self):
        c = PlateCipher(_KEY, "scope-a")
        diffs = 0
        total = 0
        for n in range(100):
            p = f"AB-{n:03d}-CD"
            sub = c.encrypt(p)
            sub_digits = sub.split("-")[1]
            if sub_digits != f"{n:03d}":
                diffs += 1
            total += 1
        # La grande majorite des chiffres doivent différer (permutation non triviale)
        assert diffs > total * 0.9


class TestDeterminismeScope:
    """Determinisme + scope distinct."""

    def test_deterministe(self):
        c = PlateCipher(_KEY, "scope-a")
        for _ in range(3):
            assert c.encrypt("AB-123-CD") == c.encrypt("AB-123-CD")

    def test_scope_distinct_differe(self):
        ca = PlateCipher(_KEY, "scope-a")
        cb = PlateCipher(_KEY, "scope-b")
        diffs = 0
        for n in range(100):
            p = f"AB-{n:03d}-CD"
            if ca.encrypt(p) != cb.encrypt(p):
                diffs += 1
        assert diffs > 0


class TestEdgeCases:
    """Cas limites."""

    def test_plaque_invalide_retourne_none(self):
        c = PlateCipher(_KEY, "scope-a")
        assert c.encrypt("invalid") is None

    def test_decrypt_substitut_invalide_retourne_none(self):
        c = PlateCipher(_KEY, "scope-a")
        assert c.decrypt("invalid") is None

    def test_zero_pad(self):
        c = PlateCipher(_KEY, "scope-a")
        sub = c.encrypt("AB-000-CD")
        assert validate(sub)
        assert sub.startswith("AB-")
        assert sub.endswith("-CD")
        assert c.decrypt(sub) == "AB-000-CD"
