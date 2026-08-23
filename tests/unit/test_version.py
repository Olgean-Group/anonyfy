"""Vérifie la cohérence version pyproject / __version__ / CHANGELOG pour v0.1.6.

Phase 47 : préparation publication 0.1.6. Correctifs recette 0.1.5 (phases
45-46) : R5 formule « Fait à ... » corrigée (fait exclu des patronymes +
indices COMMUNE formulaires), amendement D42e (communes en en-tête
`<Commune>, le <date>` désormais masquées), R6 substitut CODE_POSTAL = code
postal valide via base La Poste (Licence Ouverte 2.0). Le tag v0.1.6 et la
publication PyPI sont réservés à l'orchestrateur (après confirmation
utilisateur) ; ce test ne valide que la préparation du dépôt (version
pyproject + `__version__` du module src + en-tête CHANGELOG).
"""

import tomllib
from pathlib import Path

import anonyfy

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
CHANGELOG = REPO / "CHANGELOG.md"


def test_pyproject_version_est_0_1_6() -> None:
    with PYPROJECT.open("rb") as fh:
        project = tomllib.load(fh)["project"]
    assert project["version"] == "0.1.6"


def test_anonyfy_version_interne_egale_0_1_6() -> None:
    """Le module installé EN COURANT depuis src doit exposer __version__ == 0.1.6.

    pytest.ini fixe ``pythonpath = ["src"]``, donc ``import anonyfy`` charge le
    paquet local (src/anonyfy) et non une éventuelle version PyPI installée.
    """
    assert anonyfy.__version__ == "0.1.6"


def test_changelog_commence_par_0_1_6() -> None:
    texte = CHANGELOG.read_text(encoding="utf-8")
    assert texte.startswith("## 0.1.6")
