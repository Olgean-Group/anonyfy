"""Tests phase 46 — R6: le substitut CODE_POSTAL est un code postal valide.

R6 (recette code_review5): le « code postal » substitué était un code commune
Insee (``38117`` pour Cognet, au lieu du vrai code postal ``38350``). Le
gazetteer ``communes.csv`` ne contenait que ``code_commune``, qui alimentait
directement la substitution. Conséquence: substitut non valide en aval, F3
« substitut de même type » non tenu pour CODE_POSTAL.

D46f: quand une commune est couplée, le substitut CP est désormais le
``code_postal`` de la commune substituée (via ``code_commune`` → ``code_postal``,
base officielle La Poste embarquée), au lieu de ``dept + 3 chiffres``.
D46g: le substitut est un code postal valide (5 chiffres, présent dans la base
La Poste embarquée), pas seulement conforme au format.
"""

import re

import pytest

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import load_codes_postaux, load_communes
from anonyfy.types import EntityType

_KEY = b"0" * 16


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    yield v
    v.close()


def _base_cp_set() -> set[str]:
    """Ensemble des codes postaux valides de la base La Poste embarquée."""
    return set(load_codes_postaux().values())


def _cog_code_communes() -> set[str]:
    """Ensemble des codes communes du COG (via l'attribut code_commune)."""
    return {e.code_commune for e in load_communes() if e.code_commune}


def _mask_cp(vault, text: str) -> tuple[object, str, str]:
    """Masque ``text``, renvoie (masked, commune_substituée, cp_substitué)."""
    m = vault.mask(text)
    cp_span = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
    commune_span = [e for e in m.entities if e.type == EntityType.COMMUNE]
    assert len(cp_span) == 1, f"attendu 1 CP, trouvé {len(cp_span)}"
    assert len(commune_span) == 1, f"attendu 1 commune, trouvé {len(commune_span)}"
    return m, commune_span[0].value, cp_span[0].value


class TestSubstitutCodePostalValide:
    """D46g: le substitut CODE_POSTAL est un code postal valide de la base."""

    def test_substitut_code_postal_5_chiffres_dans_base(self, vault):
        """« Le siège est à 16000 Angoulême. » -> substitut CP valide (5 chiffres,
        présent dans la base La Poste embarquée)."""
        _m, _commune_sub, cp_sub = _mask_cp(vault, "Le siège est à 16000 Angoulême.")
        assert re.fullmatch(r"\d{5}", cp_sub), f"substitut {cp_sub!r} != 5 chiffres"
        assert cp_sub in _base_cp_set(), (
            f"substitut {cp_sub!r} n'est pas un code postal de la base La Poste"
        )

    def test_substitut_pas_code_commune_insee(self, vault):
        """Le substitut n'est pas un code commune Insee (le bug R6: 38117 était
        le code commune de Cognet, pas son code postal 38350)."""
        _m, _commune_sub, cp_sub = _mask_cp(vault, "Le siège est à 16000 Angoulême.")
        assert cp_sub != "38117"
        assert cp_sub not in _cog_code_communes(), (
            f"substitut {cp_sub!r} est un code commune Insee, pas un code postal"
        )

    def test_departement_coherent_commune_substituee(self, vault):
        """Le CP substitué appartient au département de la commune substituée (PRD §7)."""
        _m, commune_sub, cp_sub = _mask_cp(vault, "Le siège est à 16000 Angoulême.")
        gaz = load_communes()
        dept = gaz[commune_sub.casefold()].departement
        prefix = "20" if dept in ("2A", "2B") else dept
        assert cp_sub.startswith(prefix), (
            f"CP substitué {cp_sub!r} ne commence pas par le dept {prefix!r} "
            f"de la commune substituée {commune_sub!r}"
        )

    def test_substitut_est_code_postal_commune_substituee(self, vault):
        """D46f : le substitut est le code postal de la commune substituée
        (via code_commune -> code_postal), sauf sondage (point fixe == clair)."""
        _m, commune_sub, cp_sub = _mask_cp(vault, "Le siège est à 16000 Angoulême.")
        gaz = load_communes()
        codes = load_codes_postaux()
        code_commune = gaz[commune_sub.casefold()].code_commune
        expected = codes[code_commune]
        if expected != "16000":  # point fixe -> sondé par l'implémentation
            assert cp_sub == expected, (
                f"substitut {cp_sub!r} != code postal {expected!r} de la commune "
                f"substituée {commune_sub!r} (code_commune {code_commune!r})"
            )

    def test_round_trip(self, vault):
        """Round-trip : unmask(mask(t)) == t (invariants 2 et 3)."""
        t = "Le siège est à 16000 Angoulême."
        m = vault.mask(t)
        assert vault.unmask(m.text) == t


class TestF3TypeCodePostal:
    """F3 : le substitut est de même type que le clair (CODE_POSTAL)."""

    def test_f3_type_cp_est_un_code_postal_valide(self, vault):
        """Substitut 5 chiffres, dans la base, pas un code commune Insee."""
        _m, _commune_sub, cp_sub = _mask_cp(vault, "Le siège est à 16000 Angoulême.")
        assert re.fullmatch(r"\d{5}", cp_sub)
        assert cp_sub in _base_cp_set()
        assert cp_sub not in _cog_code_communes()

    def test_f3_type_trigger_sans_commune(self, vault):
        """Chemin trigger-only (CP sans commune): substitut CP valide du dept."""
        t = "Il habite à 16000."
        m = vault.mask(t)
        cp_span = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(cp_span) == 1
        cp_sub = cp_span[0].value
        assert re.fullmatch(r"\d{5}", cp_sub)
        assert cp_sub in _base_cp_set(), (
            f"substitut trigger-only {cp_sub!r} n'est pas un code postal de la base"
        )
        assert vault.unmask(m.text) == t


class TestCasLimites:
    """D46d/D46e/D46c: Corse, DOM, communes sans CP, tie-break multi-CP."""

    def test_corse_round_trip(self, vault):
        """Corse 2A/2B (mapping 2A001 -> 20167 testé au niveau loader, D46d):
        substitut CP valide de la base + round-trip."""
        t = "Il habite à 20167 Afa."
        m = vault.mask(t)
        cp_span = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(cp_span) == 1
        cp_sub = cp_span[0].value
        assert re.fullmatch(r"\d{5}", cp_sub)
        assert cp_sub in _base_cp_set()
        assert vault.unmask(m.text) == t

    def test_dom_round_trip(self, vault):
        """DOM 971: substitut CP valide de la base, round-trip."""
        t = "Il habite à 97139 Les Abymes."
        m = vault.mask(t)
        cp_span = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(cp_span) == 1
        cp_sub = cp_span[0].value
        assert re.fullmatch(r"\d{5}", cp_sub)
        assert cp_sub in _base_cp_set()
        assert vault.unmask(m.text) == t

    def test_marseille_round_trip(self, vault):
        """Marseille (13055 sans CP direct, D46c): round-trip + CP valide."""
        t = "Il habite à 13000 Marseille."
        m = vault.mask(t)
        cp_span = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(cp_span) == 1
        cp_sub = cp_span[0].value
        assert re.fullmatch(r"\d{5}", cp_sub)
        assert cp_sub in _base_cp_set()
        assert vault.unmask(m.text) == t

    def test_ajaccio_multi_cp_round_trip(self, vault):
        """Ajaccio (2A004, multi-CP 20000/20090/20167): round-trip."""
        t = "Il habite à 20000 Ajaccio."
        m = vault.mask(t)
        cp_span = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(cp_span) == 1
        cp_sub = cp_span[0].value
        assert re.fullmatch(r"\d{5}", cp_sub)
        assert cp_sub in _base_cp_set()
        assert vault.unmask(m.text) == t

    def test_deux_couples_round_trip(self, vault):
        """Round-trip avec deux couples CP/commune."""
        t = "16000 Angoulême et 75001 Paris"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t
