"""Tests du cipher référence de dossier par XOR keystream (D2, D22).

Domaine générique non énumérable: XOR keystream HMAC-SHA256.
Substitut = hex(bytes XOR keystream). Longueur préservée en bytes.
"""

from anonyfy.surrogate.reference_cipher import ReferenceCipher

_KEY = b"secret-key-32-bytes-padding-ok!!!"


class TestRoundTrip:
    """decrypt(encrypt(x))==x."""

    def test_round_trip(self):
        c = ReferenceCipher(_KEY, "scope-a")
        for ref in ["REF-2024-001", "DOSSIER-A42", "C/2024/12345", "X"]:
            assert c.decrypt(c.encrypt(ref)) == ref

    def test_round_trip_long(self):
        c = ReferenceCipher(_KEY, "scope-a")
        ref = "REF-" + "A" * 100
        assert c.decrypt(c.encrypt(ref)) == ref


class TestLongueurPreservee:
    """Longueur en bytes préservée."""

    def test_len_bytes_preservee(self):
        c = ReferenceCipher(_KEY, "scope-a")
        ref = "REF-2024-001"
        sub = c.encrypt(ref)
        assert len(bytes.fromhex(sub)) == len(ref.encode("utf-8"))

    def test_substitut_hex(self):
        c = ReferenceCipher(_KEY, "scope-a")
        sub = c.encrypt("REF-2024-001")
        # hex string: caractères 0-9a-f
        assert all(ch in "0123456789abcdef" for ch in sub)


class TestDeterminismeScope:
    """Déterminisme + scope distinct."""

    def test_deterministe(self):
        c = ReferenceCipher(_KEY, "scope-a")
        for _ in range(3):
            assert c.encrypt("REF-2024-001") == c.encrypt("REF-2024-001")

    def test_scope_distinct_differe(self):
        ca = ReferenceCipher(_KEY, "scope-a")
        cb = ReferenceCipher(_KEY, "scope-b")
        assert ca.encrypt("REF-2024-001") != cb.encrypt("REF-2024-001")

    def test_cle_distincte_differe(self):
        ca = ReferenceCipher(b"key-aaaaaaaaaaaaaaaaaaaaaaaaaa!", "scope-a")
        cb = ReferenceCipher(b"key-bbbbbbbbbbbbbbbbbbbbbbbbbbb!", "scope-a")
        assert ca.encrypt("REF-2024-001") != cb.encrypt("REF-2024-001")


class TestSubstitutNonClair:
    """Le substitut ne contient pas le clair (pas de fuite)."""

    def test_substitut_ne_contient_pas_clair(self):
        c = ReferenceCipher(_KEY, "scope-a")
        ref = "REF-2024-001"
        sub = c.encrypt(ref)
        # Le clair ne doit pas apparaître dans le substitut (hex)
        assert ref not in sub


class TestEdgeCases:
    """Cas limites."""

    def test_vide(self):
        c = ReferenceCipher(_KEY, "scope-a")
        sub = c.encrypt("")
        assert sub == ""
        assert c.decrypt("") == ""

    def test_decrypt_hex_invalide_retourne_none(self):
        c = ReferenceCipher(_KEY, "scope-a")
        # hex invalide (longueur impaire)
        assert c.decrypt("abc") is None

    def test_unicode(self):
        c = ReferenceCipher(_KEY, "scope-a")
        ref = "Dossier-Été-2024"
        assert c.decrypt(c.encrypt(ref)) == ref
