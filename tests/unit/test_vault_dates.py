"""Tests D8/critère 7: dates bucket de mois (Vault end-to-end).

Le substitut d'une date ne préserve pas jour ET mois (précision jour non
préservée, D8). Round-trip réversible pour jour <= 28. Substitut date valide.
"""

import datetime

import pytest

from anonyfy import Vault
from anonyfy.types import EntityType

_KEY = b"0" * 16


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    yield v
    v.close()


class TestCritere7DateBucket:
    """Critère 7: le substitut d'une date n'a pas même jour ET même mois."""

    def test_15_mars_1990_non_preserve(self, vault):
        m = vault.mask("né le 15 mars 1990")
        sub = [e for e in m.entities if e.type == EntityType.DATE][0]
        d = _parse_date(sub.value)
        assert d is not None
        assert d.day != 15 or d.month != 3

    def test_3_mai_1990_non_preserve(self, vault):
        m = vault.mask("né le 3 mai 1990")
        sub = [e for e in m.entities if e.type == EntityType.DATE][0]
        d = _parse_date(sub.value)
        assert d is not None
        assert d.day != 3 or d.month != 5

    def test_substitut_date_valide(self, vault):
        m = vault.mask("né le 15 mars 1990")
        sub = [e for e in m.entities if e.type == EntityType.DATE][0]
        d = _parse_date(sub.value)
        assert d is not None
        assert datetime.date(1900, 1, 1) <= d <= datetime.date(2100, 12, 31)


class TestRoundTripDate:
    """Round-trip réversible pour jour <= 28."""

    def test_round_trip_15_mars_1990(self, vault):
        t = "né le 15 mars 1990"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_round_trip_3_mai_1990(self, vault):
        t = "né le 3 mai 1990"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_round_trip_slash(self, vault):
        t = "Date: 15/03/1990"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t


class TestPasDeFuiteDate:
    """La date claire ne doit pas apparaître dans m.text."""

    def test_15_mars_absent(self, vault):
        m = vault.mask("né le 15 mars 1990")
        assert "15 mars 1990" not in m.text


def _parse_date(s: str) -> datetime.date | None:
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
