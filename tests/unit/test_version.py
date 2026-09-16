"""Vérifie la cohérence version pyproject / __version__ / CHANGELOG pour v0.1.10.

Phase 58 : préparation de la publication 0.1.10. Correctif de performance :
`Vault.mask` détectait deux fois sur le chemin par défaut (OBJ-009, phase 57),
la détection passant de ~104 ms à ~48 ms sur un texte dense. Le tag v0.1.10 et
la publication PyPI sont réservés à l'orchestrateur ; ce test ne valide que la
préparation du dépôt (version pyproject + ``__version__`` du module src +
en-tête CHANGELOG).
"""

import tomllib
from pathlib import Path

import anonyfy

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
CHANGELOG = REPO / "CHANGELOG.md"


def test_pyproject_version_est_0_1_10() -> None:
    with PYPROJECT.open("rb") as fh:
        project = tomllib.load(fh)["project"]
    assert project["version"] == "0.1.10"


def test_anonyfy_version_interne_egale_0_1_10() -> None:
    """Le module installé EN COURANT depuis src doit exposer __version__ == 0.1.10.

    pytest.ini fixe ``pythonpath = ["src"]``, donc ``import anonyfy`` charge le
    paquet local (src/anonyfy) et non une éventuelle version PyPI installée.
    """
    assert anonyfy.__version__ == "0.1.10"


def test_changelog_commence_par_0_1_10() -> None:
    texte = CHANGELOG.read_text(encoding="utf-8")
    assert texte.startswith("## 0.1.10")
