"""Vérifie la cohérence version pyproject / __version__ / CHANGELOG pour v0.1.3.

Phase 37 : préparation publication 0.1.3. Correctifs recette 0.1.2 (phases
34-36) : R1 (précision patronymes/prénoms, déclencheur requis + exclusion
mots-outils), R2 (permutation paresseuse, premier mask < 3 s), S1 (filet
global anti-fuite + détection patronymes composés), B2 (restitution casse des
noms composés à trait d'union et article élidé). Le tag v0.1.3 et la
publication PyPI sont réservés à l'orchestrateur (après confirmation
utilisateur) ; ce test ne valide que la préparation du dépôt
(version pyproject + `__version__` du module src + en-tête CHANGELOG).
"""

import tomllib
from pathlib import Path

import anonyfy

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
CHANGELOG = REPO / "CHANGELOG.md"


def test_pyproject_version_est_0_1_3() -> None:
    with PYPROJECT.open("rb") as fh:
        project = tomllib.load(fh)["project"]
    assert project["version"] == "0.1.3"


def test_anonyfy_version_interne_egale_0_1_3() -> None:
    """Le module installé EN COURANT depuis src doit exposer __version__ == 0.1.3.

    pytest.ini fixe ``pythonpath = ["src"]``, donc ``import anonyfy`` charge le
    paquet local (src/anonyfy) et non une éventuelle version PyPI installée.
    """
    assert anonyfy.__version__ == "0.1.3"


def test_changelog_commence_par_0_1_3() -> None:
    texte = CHANGELOG.read_text(encoding="utf-8")
    assert texte.startswith("## 0.1.3")
