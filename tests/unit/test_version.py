"""Vérifie la cohérence version pyproject / __version__ / CHANGELOG pour v0.1.11.

Phase 66 : préparation de la publication 0.1.11. Correctif de sûreté : la
collision de substituts inter-type (PRENOM/PATRONYME) faisait échouer `mask`
(8 249 cas mesurés sur 23 227 prénoms purs), et le point fixe sondé n'était pas
réversible. Également : mois NIR calendaire, repli genre averti, assertion
d'invariant durcie. Le tag v0.1.11 et la publication PyPI sont réservés à
l'orchestrateur ; ce test ne valide que la préparation du dépôt (version
pyproject + ``__version__`` du module src + en-tête CHANGELOG).
"""

import tomllib
from pathlib import Path

import anonyfy

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
CHANGELOG = REPO / "CHANGELOG.md"


def test_pyproject_version_est_0_1_11() -> None:
    with PYPROJECT.open("rb") as fh:
        project = tomllib.load(fh)["project"]
    assert project["version"] == "0.1.11"


def test_anonyfy_version_interne_egale_0_1_11() -> None:
    """Le module installé EN COURANT depuis src doit exposer __version__ == 0.1.11.

    pytest.ini fixe ``pythonpath = ["src"]``, donc ``import anonyfy`` charge le
    paquet local (src/anonyfy) et non une éventuelle version PyPI installée.
    """
    assert anonyfy.__version__ == "0.1.11"


def test_changelog_commence_par_0_1_11() -> None:
    texte = CHANGELOG.read_text(encoding="utf-8")
    assert texte.startswith("## 0.1.11")
