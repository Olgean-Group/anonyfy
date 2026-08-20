"""Tests D2/critères 11, 12: plaque SIV + référence dossier (Vault end-to-end).

Critère 11: plaque SIV via registre (permutation [0,1000)), round-trip.
Critère 12: référence de dossier via registre (XOR keystream), round-trip.
"""

import pytest

from anonyfy import Vault

_KEY = b"0" * 16


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    yield v
    v.close()


class TestCritere11PlaqueSIV:
    """Plaque SIV: permutation [0,1000), lettres préservées, round-trip."""

    def test_round_trip_plaque(self, vault):
        t = "plaque AB-123-CD"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_chiffres_non_preserves(self, vault):
        t = "plaque AB-123-CD"
        m = vault.mask(t)
        # Le substitut ne doit pas contenir "123" (ou pas AB-123-CD identique)
        assert "123" not in m.text or m.text.count("AB-123-CD") == 0

    def test_lettres_preservees(self, vault):
        t = "plaque AB-123-CD"
        m = vault.mask(t)
        # Les lettres AB et CD sont préservées dans le substitut
        assert "AB-" in m.text
        assert "-CD" in m.text

    def test_round_trip_plaque_3_lettres(self, vault):
        t = "plaque AB-456-CDE"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t


class TestCritere12ReferenceDossier:
    """Référence dossier: XOR keystream, round-trip."""

    def test_round_trip_reference(self, tmp_path):
        v = Vault(
            key=_KEY,
            scope="s",
            registry_path=str(tmp_path / "r.db"),
            reference_patterns=[r"DOS-\d{6}"],
        )
        t = "Dossier DOS-123456"
        m = v.mask(t)
        assert v.unmask(m.text) == t
        v.close()

    def test_reference_non_claire(self, tmp_path):
        v = Vault(
            key=_KEY,
            scope="s",
            registry_path=str(tmp_path / "r.db"),
            reference_patterns=[r"DOS-\d{6}"],
        )
        t = "Dossier DOS-123456"
        m = v.mask(t)
        assert "DOS-123456" not in m.text
        v.close()

    def test_round_trip_reference_long(self, tmp_path):
        v = Vault(
            key=_KEY,
            scope="s",
            registry_path=str(tmp_path / "r.db"),
            reference_patterns=[r"REF-\d{4}-\d{3}"],
        )
        t = "Référence REF-2024-001"
        m = v.mask(t)
        assert v.unmask(m.text) == t
        v.close()
