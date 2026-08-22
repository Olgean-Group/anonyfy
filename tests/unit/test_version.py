"""Vérifie la cohérence version pyproject / CHANGELOG pour la republication v0.1.1.

Phase 33 : préparation republication. Le tag v0.1.1 et la publication PyPI
sont réservés à l'orchestrateur (après confirmation utilisateur) ; ce test ne
valide que la préparation du dépôt (version + changelog).
"""

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
CHANGELOG = REPO / "CHANGELOG.md"


def test_pyproject_version_est_0_1_1() -> None:
    with PYPROJECT.open("rb") as fh:
        project = tomllib.load(fh)["project"]
    assert project["version"] == "0.1.1"


def test_changelog_commence_par_0_1_1() -> None:
    texte = CHANGELOG.read_text(encoding="utf-8")
    assert texte.startswith("## 0.1.1")
