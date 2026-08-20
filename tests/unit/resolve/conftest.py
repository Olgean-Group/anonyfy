"""Fixtures pour les tests resolve (phase 10b).

Expose un registre pré-rempli via ``ScopeRegistry.reserve(...)`` (phase 10) pour
les tests d'intégration registre→automate, et une liste de **substituts** de
test connus (surrogates, pas le clair) pour les tests purs de variantes.

Le registre ne stocke jamais de valeur claire (invariant 1, D4). Les substituts
émis par ``reserve`` sont des chaînes d'indice déterministes scopées (pas le
clair).

Référence: PLAN.md phase 10b, D7/OBJ-005.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anonyfy.surrogate.registry import ScopeRegistry

ZERO_KEY = b"0" * 16
SCOPE = "phase-10b-tests"

# Substituts de test connus (surrogates, PAS le clair) pour les tests purs de
# variantes en isolation: un SIRET FPE-valide et un patronyme de gazetteer.
KNOWN_SURROGATES: list[str] = ["41804261100034", "Pierre Dupont"]


@pytest.fixture()
def registry_path(tmp_path: Path) -> str:
    return str(tmp_path / "resolve_reg.db")


@pytest.fixture()
def registry(registry_path: str):
    r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
    yield r
    r.close()


@pytest.fixture()
def registry_with_entries(registry: ScopeRegistry):
    """Registre pré-rempli via ``reserve(...)``.

    Renvoie ``(registre, premier_substitut_émis)``. Le substitut est une chaîne
    d'indice (pas le clair « Jean »), conformément à l'invariant 1.
    """
    sub = registry.reserve("prenom", "Jean", gazetteer_size=50000)
    return registry, sub
