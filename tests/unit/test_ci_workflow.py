"""Validation statique du workflow GitHub Actions de la phase 02.

Un workflow GitHub Actions ne s'exécute pas localement comme du code Python.
La méthode TDD s'adapte: ce test est le "rouge" qui échoue tant que le fichier
workflow n'existe pas ou ne respecte pas le contrat de la phase 02 (matrice
Python 3.11/3.12/3.13, étapes ruff check + ruff format --check + pytest).

Le test peut échouer pour de vraies raisons:
- le fichier `.github/workflows/ci.yml` n'existe pas,
- le YAML est malformé,
- la matrice Python n'est pas exactement {3.11, 3.12, 3.13},
- une étape de CI requise est absente.

Il ne valide pas la sémantique d'exécution (déclenchement réel sur GitHub), qui
est couverte par les critères d'acceptation `gh run ...` de la phase 02.
"""

from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

REQUIRED_PYTHON_VERSIONS = ["3.11", "3.12", "3.13"]


def _load_workflow() -> dict:
    """Charge et parse le workflow CI en YAML. Échoue s'il est absent/malformé."""
    assert WORKFLOW_PATH.exists(), f"workflow manquant: {WORKFLOW_PATH}"
    with WORKFLOW_PATH.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict), "le workflow n'est pas un mapping YAML valide"
    return data


def _ci_steps_text(workflow: dict) -> str:
    """Concatène le texte de tous les `run` des jobs pour inspection."""
    jobs = workflow.get("jobs", {})
    assert isinstance(jobs, dict) and jobs, "aucun job défini dans le workflow"
    chunks: list[str] = []
    for job in jobs.values():
        assert isinstance(job, dict), "un job n'est pas un mapping"
        steps = job.get("steps", [])
        assert isinstance(steps, list), "steps manquants ou non-liste dans un job"
        for step in steps:
            assert isinstance(step, dict), "un step n'est pas un mapping"
            if "run" in step:
                chunks.append(str(step["run"]))
    joined = "\n".join(chunks)
    assert joined.strip(), "aucun step 'run' trouvé dans le workflow"
    return joined


def test_workflow_file_exists() -> None:
    """Le fichier de workflow CI est présent à l'emplacement attendu."""
    assert WORKFLOW_PATH.is_file(), f"ci.yml absent à {WORKFLOW_PATH}"


def test_workflow_is_valid_yaml_mapping() -> None:
    """Le workflow est un mapping YAML parsable (pas une liste ou un scalaire)."""
    data = _load_workflow()
    # NB: PyYAML (YAML 1.1) convertit la clé `on:` en booléen Python ``True``.
    # On accepte les deux formes comme déclencheur valide.
    assert "on" in data or True in data, "déclencheur 'on' manquant"
    assert "jobs" in data, "section 'jobs' manquante"


def test_matrix_runs_three_python_versions() -> None:
    """La matrice exécute bien Python 3.11, 3.12 et 3.13."""
    data = _load_workflow()
    jobs = data["jobs"]
    matrix_versions: list[str] = []
    for job in jobs.values():
        strategy = job.get("strategy", {})
        matrix = strategy.get("matrix", {})
        versions = matrix.get("python-version", [])
        if versions:
            matrix_versions = list(versions)
            break
    assert matrix_versions, "aucune matrice python-version trouvée dans un job"
    assert sorted(matrix_versions) == REQUIRED_PYTHON_VERSIONS, (
        f"matrice Python attendue {REQUIRED_PYTHON_VERSIONS}, trouvée {matrix_versions}"
    )


def test_workflow_runs_ruff_check() -> None:
    """Le workflow contient une étape `ruff check`."""
    assert "ruff check" in _ci_steps_text(_load_workflow())


def test_workflow_runs_ruff_format_check() -> None:
    """Le workflow contient une étape `ruff format --check`."""
    assert "ruff format --check" in _ci_steps_text(_load_workflow())


def test_workflow_runs_pytest() -> None:
    """Le workflow contient une étape `pytest`."""
    assert "pytest" in _ci_steps_text(_load_workflow())


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
