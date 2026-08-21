"""Critère d'acceptation 6: déterminisme — 1000 exécutions -> sortie identique.

On masque un même texte 1000 fois avec la même clé et le même scope, et on
vérifie que la sortie (m.text) est bit à bit identique à chaque exécution. Le
registre réutilise le substitut enregistré au premier appel, garantissant la
répétabilité (invariant 2: déterminisme scopé).

Référence: PRD §10 critère 6, PLAN.md phase 19.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault

_KEY = b"0" * 16
_SCOPE = "acceptance-determinism"

# Texte couvrant plusieurs types (patronyme, date, SIRET) pour un déterminisme
# représentatif.
_TEXT = "M. Jean Dupont, né le 3 mai 1990, SIRET 73282932000033"
_N = 1000


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


def test_determinism_1000_executions(vault):
    """1000 exécutions de mask sur le même texte -> sortie identique."""
    first = vault.mask(_TEXT).text
    for _ in range(_N - 1):
        out = vault.mask(_TEXT).text
        assert out == first, "determinisme rompu: mask produit des sorties différentes"
    # Vérification bit à bit: la première sortie est réutilisée à l'identique.
    assert first == vault.mask(_TEXT).text
