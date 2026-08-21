"""Critère d'acceptation D14: débit FPE — substituts/s sur 100 000 identifiants.

Mesure le débit de masquage (substituts par seconde) sur 100 000 identifiants
structurés (SIRET). Test informatif et **non bloquant** pour v1 (D14): il passe
dès que le débit mesuré est strictement positif, et affiche la mesure pour
documentation. La cible est documentée dans le rapport d'acceptation
(``scripts/acceptance_report.py``), pas assertée ici.

Référence: PRD §10 D14, PLAN.md phase 19.
"""

from __future__ import annotations

import time

import pytest

from anonyfy import Vault

_KEY = b"0" * 16
_SCOPE = "acceptance-throughput"
_N_IDENTIFIERS = 100_000

# 10 SIRET distincts par texte, masqués 10 000 fois -> 100 000 identifiants.
_SIRETS = [
    "73282932000033",
    "73282932000034",
    "73282932000035",
    "73282932000036",
    "73282932000037",
    "73282932000038",
    "73282932000039",
    "73282932000040",
    "73282932000041",
    "73282932000042",
]
_TEXT = " ".join(f"SIRET {s}" for s in _SIRETS)
_N_CALLS = _N_IDENTIFIERS // len(_SIRETS)


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


def test_fpe_throughput_100k_identifiers(vault):
    """Débit FPE sur 100 000 identifiants: mesure > 0 (non bloquant, D14)."""
    vault.mask(_TEXT)  # échauffement (peuple le registre)
    start = time.perf_counter()
    for _ in range(_N_CALLS):
        vault.mask(_TEXT)
    elapsed = time.perf_counter() - start
    throughput = _N_IDENTIFIERS / elapsed if elapsed > 0 else 0.0
    # Non bloquant: on asserte uniquement que la mesure est positive.
    assert throughput > 0, "débit mesuré nul"
    # Documente la mesure pour le rapport (cible non assertée, D14).
    print(f"\n[D14] débit FPE: {throughput:.0f} substituts/s sur {_N_IDENTIFIERS} identifiants")
