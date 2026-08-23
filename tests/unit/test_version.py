"""Vérifie la cohérence version pyproject / __version__ / CHANGELOG pour v0.1.5.

Phase 44 : préparation publication 0.1.5. Correctifs recette 0.1.4 (phases
42-43) : précision COMMUNE/VOIE par indices stricts (verbes d'adresse + CP
adjacent pour COMMUNE, type de voie + numéro pour VOIE), corpus négatif
régénéré par intersection mots courants x gazetteers (précision 1.000),
généralisation de la règle de confiance (aucun span < 0.8 en permissive sans
indice contextuel), et limitation annoncée : les communes sans indice
d'adresse fort (prose « Je vais à Paris », en-têtes de lettre « Paris, le 23
août ») ne sont pas masquées en permissive. Le tag v0.1.5 et la publication
PyPI sont réservés à l'orchestrateur (après confirmation utilisateur) ; ce
test ne valide que la préparation du dépôt (version pyproject + `__version__`
du module src + en-tête CHANGELOG).
"""

import tomllib
from pathlib import Path

import anonyfy

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
CHANGELOG = REPO / "CHANGELOG.md"


def test_pyproject_version_est_0_1_5() -> None:
    with PYPROJECT.open("rb") as fh:
        project = tomllib.load(fh)["project"]
    assert project["version"] == "0.1.5"


def test_anonyfy_version_interne_egale_0_1_5() -> None:
    """Le module installé EN COURANT depuis src doit exposer __version__ == 0.1.5.

    pytest.ini fixe ``pythonpath = ["src"]``, donc ``import anonyfy`` charge le
    paquet local (src/anonyfy) et non une éventuelle version PyPI installée.
    """
    assert anonyfy.__version__ == "0.1.5"


def test_changelog_commence_par_0_1_5() -> None:
    texte = CHANGELOG.read_text(encoding="utf-8")
    assert texte.startswith("## 0.1.5")
