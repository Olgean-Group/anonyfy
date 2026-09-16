"""Test canari du paquet anonyfy (phase 01).

Valide que le paquet s'importe et que ``__version__`` correspond à
``pyproject.toml``. La version attendue est lue (REV-MIN-5, OBJ-108): le bump
d'une source sans l'autre fait échouer ce test sans re-coder la version ici.

Référence: PLAN.md phase 01, BACKLOG REV-MIN-5.
"""

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def test_anonyfy_importable_with_version() -> None:
    import anonyfy

    with PYPROJECT.open("rb") as fh:
        expected = tomllib.load(fh)["project"]["version"]
    assert anonyfy.__version__ == expected
