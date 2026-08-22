"""Vitrine PyPI : critères M1/M2/M5 (phase 29).

Vérifie la cohérence de la description et des métadonnées publiées sur PyPI :
- M5 : la description ne contient pas « anonymisation » (l'anonymisation est
  irréversible par définition ; le positionnement PRD §9 est pseudonymisation).
- M5 : la description contient « pseudonymisation ».
- M1 : l'URL Homepage pointe vers Olgean-Group/anonyfy.
- M2 : la licence est Apache-2.0.
"""

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _load_project() -> dict:
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["project"]


def test_m5_description_sans_anonymisation() -> None:
    project = _load_project()
    assert "anonymisation" not in project["description"].lower()


def test_m5_description_contient_pseudonymisation() -> None:
    project = _load_project()
    assert "pseudonymisation" in project["description"].lower()


def test_m1_homepage_olgean_group_anonyfy() -> None:
    project = _load_project()
    assert "Olgean-Group/anonyfy" in project["urls"]["Homepage"]


def test_m2_license_apache_2() -> None:
    project = _load_project()
    assert project["license"] == "Apache-2.0"
