"""Tests D9/critères 9, 10: email local-part (Vault end-to-end).

Critère 9: round-trip sur forme régularisée (NFKC + minuscules).
Critère 10: corpus accents, apostrophes, points multiples, longueur 64.
"""

import pytest

from anonyfy import Vault

_KEY = b"0" * 16


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    yield v
    v.close()


class TestCritere9RoundTripRegularise:
    """Round-trip sur forme régularisée (jean.o'brien@exemple.fr)."""

    def test_round_trip_forme_regularisee(self, vault):
        t = "Contact: Jean.O'Brien@exemple.fr"
        m = vault.mask(t)
        assert vault.unmask(m.text) == "Contact: jean.o'brien@exemple.fr"

    def test_jean_absent(self, vault):
        t = "Contact: Jean.O'Brien@exemple.fr"
        m = vault.mask(t)
        assert "Jean" not in m.text

    def test_domaine_intact(self, vault):
        t = "Contact: jean.o'brien@exemple.fr"
        m = vault.mask(t)
        assert "exemple.fr" in m.text


class TestCritere10Corpus:
    """Corpus: accents, apostrophes, points multiples, longueur 64."""

    def test_accents(self, vault):
        # Accent hors alphabet -> repli keystream (round-trip marche)
        t = "Mail: étienne.été@exemple.fr"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_apostrophes(self, vault):
        t = "Mail: jean.o'brien@exemple.fr"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_points_multiples(self, vault):
        t = "Mail: jean.pierre.marie.dupont@exemple.fr"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_longueur_64(self, vault):
        lp = "a" * 64
        t = f"Mail: {lp}@exemple.fr"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t


class TestPasDeFuiteEmail:
    """Le local-part clair ne doit pas apparaître dans m.text."""

    def test_localpart_clair_absent(self, vault):
        t = "Contact: jean.o'brien@exemple.fr"
        m = vault.mask(t)
        assert "jean" not in m.text.split("@")[0]
        assert "o'brien" not in m.text.split("@")[0]