"""Vérifie la cohérence version pyproject / __version__ / CHANGELOG pour v0.1.8.

Phase 54 : préparation de la publication 0.1.8. Correctifs de sûreté et dettes
de la revue S8 : fuite CP trigger-only (REV-MIN-2, ~1 % des CP sans commune
restaient en clair), typage COMMUNE sur verbe d'adresse (REV-MAJ-1, phase 50),
invariant F3-type formalisé, `flush()` public, chargement registre unique,
snapshot ff3, canaris paramétriques, latence dense robuste. Le tag v0.1.8 et la
publication PyPI sont réservés à l'orchestrateur ; ce test ne valide que la
préparation du dépôt (version pyproject + ``__version__`` du module src +
en-tête CHANGELOG).
"""

import tomllib
from pathlib import Path

import anonyfy

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
CHANGELOG = REPO / "CHANGELOG.md"


def test_pyproject_version_est_0_1_8() -> None:
    with PYPROJECT.open("rb") as fh:
        project = tomllib.load(fh)["project"]
    assert project["version"] == "0.1.8"


def test_anonyfy_version_interne_egale_0_1_8() -> None:
    """Le module installé EN COURANT depuis src doit exposer __version__ == 0.1.8.

    pytest.ini fixe ``pythonpath = ["src"]``, donc ``import anonyfy`` charge le
    paquet local (src/anonyfy) et non une éventuelle version PyPI installée.
    """
    assert anonyfy.__version__ == "0.1.8"


def test_changelog_commence_par_0_1_8() -> None:
    texte = CHANGELOG.read_text(encoding="utf-8")
    assert texte.startswith("## 0.1.8")
