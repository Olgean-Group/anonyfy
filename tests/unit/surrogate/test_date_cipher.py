"""Tests du cipher date par permutation (D8, D22).

Permutation sur [0, N) où N = 201 ans * 12 mois * 28 jours (jour clampé à [1,28]
pour garantir réversibilité: 28 existe dans tous les mois). D8: précision jour
non préservée pour jours > 28 (clampé, documenté). Critère 7: le substitut d'une
date n'a pas même jour ET même mois (généralement).

Formats acceptés: JJ/MM/AAAA et "JJ mois AAAA" (textuel FR).
"""

import datetime

from anonyfy.surrogate.date_cipher import DateCipher

_KEY = b"secret-key-32-bytes-padding-ok!!!"


class TestRoundTrip:
    """decrypt(encrypt(x))==x pour jour <= 28."""

    def test_round_trip_jj_mois_aaaa(self):
        c = DateCipher(_KEY, "scope-a")
        for d in ["15 mars 1990", "3 mai 2020", "1 janvier 1900", "28 decembre 2100"]:
            assert c.decrypt(c.encrypt(d)) == d

    def test_round_trip_slash(self):
        c = DateCipher(_KEY, "scope-a")
        for d in ["15/03/1990", "03/05/2020", "01/01/1900", "28/12/2100"]:
            assert c.decrypt(c.encrypt(d)) == d


class TestCritere7Bucket:
    """D8/critère 7: le substitut ne préserve pas jour ET mois."""

    def test_15_mars_1990_non_preserve(self):
        c = DateCipher(_KEY, "scope-a")
        sub = c.encrypt("15 mars 1990")
        # Le substitut est une date valide; parser
        d = _parse_date(sub)
        assert d is not None
        # jour != 15 OR mois != 3
        assert d.day != 15 or d.month != 3

    def test_substitut_date_valide(self):
        c = DateCipher(_KEY, "scope-a")
        sub = c.encrypt("15 mars 1990")
        d = _parse_date(sub)
        assert d is not None
        assert datetime.date(1900, 1, 1) <= d <= datetime.date(2100, 12, 31)


class TestClampJour:
    """Jour > 28 clampé à 28 (perte documentée, D8)."""

    def test_jour_31_round_trip_echoue(self):
        # 31 clampé à 28: round-trip retourne 28, pas 31 (limite D8)
        c = DateCipher(_KEY, "scope-a")
        sub = c.encrypt("31 mars 1990")
        result = c.decrypt(sub)
        # Le jour est clampé à 28
        assert "28" in result

    def test_jour_29_round_trip(self):
        c = DateCipher(_KEY, "scope-a")
        sub = c.encrypt("29 mars 1990")
        result = c.decrypt(sub)
        # 29 clampé à 28
        assert "28" in result


class TestDeterminismeScope:
    """Déterminisme + scope distinct."""

    def test_deterministe(self):
        c = DateCipher(_KEY, "scope-a")
        for _ in range(3):
            assert c.encrypt("15 mars 1990") == c.encrypt("15 mars 1990")

    def test_scope_distinct_differe(self):
        ca = DateCipher(_KEY, "scope-a")
        cb = DateCipher(_KEY, "scope-b")
        assert ca.encrypt("15 mars 1990") != cb.encrypt("15 mars 1990")


class TestFormatPreserve:
    """Le format d'entrée est préservé dans le substitut."""

    def test_format_textuel_preserve(self):
        c = DateCipher(_KEY, "scope-a")
        sub = c.encrypt("15 mars 1990")
        # Format "JJ mois AAAA" (contient un mot de mois)
        mois_noms = [
            "janvier",
            "fevrier",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "aout",
            "septembre",
            "octobre",
            "novembre",
            "decembre",
        ]
        assert any(m in sub for m in mois_noms)

    def test_format_slash_preserve(self):
        c = DateCipher(_KEY, "scope-a")
        sub = c.encrypt("15/03/1990")
        assert "/" in sub


class TestEdgeCases:
    """Cas limites."""

    def test_format_invalide_retourne_none(self):
        c = DateCipher(_KEY, "scope-a")
        assert c.encrypt("invalid") is None

    def test_decrypt_format_invalide_retourne_none(self):
        c = DateCipher(_KEY, "scope-a")
        assert c.decrypt("invalid") is None

    def test_date_hors_plage_retourne_none(self):
        c = DateCipher(_KEY, "scope-a")
        assert c.encrypt("15 mars 1899") is None
        assert c.encrypt("15 mars 2101") is None


def _parse_date(s: str) -> datetime.date | None:
    """Parse une date JJ/MM/AAAA ou JJ mois AAAA."""
    import re

    months = {
        "janvier": 1,
        "fevrier": 2,
        "mars": 3,
        "avril": 4,
        "mai": 5,
        "juin": 6,
        "juillet": 7,
        "aout": 8,
        "septembre": 9,
        "octobre": 10,
        "novembre": 11,
        "decembre": 12,
    }
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})\s+(\w+)\s+(\d{4})", s, re.IGNORECASE)
    if m:
        mois = months.get(m.group(2).lower())
        if mois is None:
            return None
        try:
            return datetime.date(int(m.group(3)), mois, int(m.group(1)))
        except ValueError:
            return None
    return None
