"""Test canari de la phase 02.

Asserte que le paquet ``anonyfy`` est importable et que sa version interne est
celle de ``pyproject.toml``. La version attendue est lue (REV-MIN-5, OBJ-108):
un bump de ``pyproject.toml`` suivi d'un oubli de ``__version__`` fait échouer
ce test, sans re-coder la version en dur ici.

Référence: PLAN.md phase 02, BACKLOG REV-MIN-5.
"""

import tomllib
from pathlib import Path

import anonyfy

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_smoke_imports_anonyfy() -> None:
    with PYPROJECT.open("rb") as fh:
        expected = tomllib.load(fh)["project"]["version"]
    assert anonyfy.__version__ == expected
