"""Tests du cipher email local-part par permutation (D9, D22).

Normalisation NFKC + minuscules. Alphabet effectif a-z0-9.+-'.
Permutation sur [0, 38^L). Repli keystream pour L < 4 ou char hors alphabet.
Domaine en clair. Round-trip sur forme régularisée (D9 limite documentée).
"""

import unicodedata

from anonyfy.surrogate.email_cipher import EmailCipher

_KEY = b"secret-key-32-bytes-padding-ok!!!"


def _normalize(lp: str) -> str:
    return unicodedata.normalize("NFKC", lp).casefold()


class TestRoundTripPermutation:
    """Round-trip sur local-parts dans l'alphabet (L >= 4)."""

    def test_round_trip_jean_obrien(self):
        c = EmailCipher(_KEY, "scope-a")
        sub, mode = c.encrypt("jean.o'brien@exemple.fr")
        assert c.decrypt(sub, mode) == "jean.o'brien@exemple.fr"

    def test_round_trip_long(self):
        c = EmailCipher(_KEY, "scope-a")
        lp = "a" * 64
        sub, mode = c.encrypt(f"{lp}@exemple.fr")
        assert c.decrypt(sub, mode) == f"{lp}@exemple.fr"

    def test_round_trip_points_multiples(self):
        c = EmailCipher(_KEY, "scope-a")
        sub, mode = c.encrypt("jean.pierre.marie.dupont@exemple.fr")
        assert c.decrypt(sub, mode) == "jean.pierre.marie.dupont@exemple.fr"


class TestFormeRegularisee:
    """D9: round-trip sur forme régularisée (NFKC + minuscules)."""

    def test_forme_regularisee(self):
        c = EmailCipher(_KEY, "scope-a")
        # Forme originale avec majuscules -> régularisée (local-part only, domaine en clair)
        sub, mode = c.encrypt("Jean.O'Brien@exemple.fr")
        # decrypt retourne la forme régularisée du local-part, domaine préservé
        assert c.decrypt(sub, mode) == "jean.o'brien@exemple.fr"

    def test_apostrophe_u0027_preservee(self):
        c = EmailCipher(_KEY, "scope-a")
        sub, mode = c.encrypt("jean.o'brien@exemple.fr")
        result = c.decrypt(sub, mode)
        assert "'" in result  # U+0027


class TestDomaineClair:
    """Le domaine n'est pas masqué."""

    def test_domaine_clair(self):
        c = EmailCipher(_KEY, "scope-a")
        sub, mode = c.encrypt("jean.o'brien@exemple.fr")
        assert sub.endswith("@exemple.fr")

    def test_domaine_clair_casse_preservee(self):
        c = EmailCipher(_KEY, "scope-a")
        sub, mode = c.encrypt("jean@Exemple.FR")
        # Domaine en clair, casse préservée
        assert sub.endswith("@Exemple.FR")


class TestLongueurPreservee:
    """Longueur local-part préservée (mode permutation)."""

    def test_len_localpart_preservee_perm(self):
        c = EmailCipher(_KEY, "scope-a")
        email = "jean.o'brien@exemple.fr"
        sub, mode = c.encrypt(email)
        if mode == "perm":
            sub_lp = sub.split("@")[0]
            orig_lp = _normalize(email.split("@")[0])
            assert len(sub_lp) == len(orig_lp)


class TestRepliKeystream:
    """L < 4 ou char hors alphabet -> repli keystream (round-trip marche)."""

    def test_localpart_courte_keystream(self):
        c = EmailCipher(_KEY, "scope-a")
        sub, mode = c.encrypt("ab@exemple.fr")
        assert mode == "keystream"
        assert c.decrypt(sub, mode) == "ab@exemple.fr"

    def test_localpart_1_char_keystream(self):
        c = EmailCipher(_KEY, "scope-a")
        sub, mode = c.encrypt("a@exemple.fr")
        assert mode == "keystream"
        assert c.decrypt(sub, mode) == "a@exemple.fr"

    def test_localpart_accent_keystream(self):
        # é hors alphabet a-z -> repli keystream
        c = EmailCipher(_KEY, "scope-a")
        sub, mode = c.encrypt("étienne.été@exemple.fr")
        assert mode == "keystream"
        assert c.decrypt(sub, mode) == "étienne.été@exemple.fr"


class TestDeterminismeScope:
    """Déterminisme + scope distinct."""

    def test_deterministe(self):
        c = EmailCipher(_KEY, "scope-a")
        s1, _ = c.encrypt("jean.o'brien@exemple.fr")
        s2, _ = c.encrypt("jean.o'brien@exemple.fr")
        assert s1 == s2

    def test_scope_distinct_differe(self):
        ca = EmailCipher(_KEY, "scope-a")
        cb = EmailCipher(_KEY, "scope-b")
        s1, _ = ca.encrypt("jean.o'brien@exemple.fr")
        s2, _ = cb.encrypt("jean.o'brien@exemple.fr")
        assert s1 != s2


class TestPasDeFuite:
    """Le local-part clair ne doit pas apparaître dans le substitut."""

    def test_localpart_clair_absent(self):
        c = EmailCipher(_KEY, "scope-a")
        sub, mode = c.encrypt("jean.o'brien@exemple.fr")
        assert "jean" not in sub.split("@")[0]
        assert "o'brien" not in sub.split("@")[0]
