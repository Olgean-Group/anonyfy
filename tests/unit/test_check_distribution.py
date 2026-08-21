"""Garde-fou de distribution anonyfy (phase 22).

Valide ``scripts/check_distribution.py``: un script stdlib qui inspecte le
contenu des artefacts ``dist/`` (sdist ``.tar.gz`` + wheel ``.whl``) et quitte
avec code 1 si un fichier ou chemin interdit s'y trouve.

Fichiers/chemins interdits dans une distribution anonyfy:
  - ``.olgenius/``      (état de pilotage local)
  - ``resume.md``       (mémoire de session)
  - ``*.bak``           (sauvegardes)
  - ``corpus_real/``    (corpus réel RGPD, jamais dans le dépôt)
  - ``__pycache__/``    (bytecode)
  - ``*.pyc``           (bytecode)
  - ``.gitignore``      (config locale de dépôt)

Le test construit de fausses archives (``tarfile``/``zipfile``) en mémoire et
invoque le script en sous-processus pour valider le vrai contrat de sortie
(code de exit). Un test qui ne peut pas échouer pour une vraie raison est du
bruit; on teste donc les deux branches (propre -> 0, interdit -> 1) et plusieurs
variantes du motif interdit.
"""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_distribution.py"


def _run_script(*paths: Path) -> subprocess.CompletedProcess[str]:
    """Invoque le script en sous-processus avec les chemins donnés."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(p) for p in paths)],
        capture_output=True,
        text=True,
        check=False,
    )


def _make_sdist(path: Path, members: dict[str, bytes]) -> Path:
    """Construit une sdist .tar.gz avec les membres ``name -> content``."""
    with tarfile.open(path, "w:gz") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name=name)
            data = content if isinstance(content, bytes) else content.encode()
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def _make_wheel(path: Path, members: dict[str, bytes]) -> Path:
    """Construit une wheel .whl (zip) avec les membres ``name -> content``."""
    with zipfile.ZipFile(path, "w") as z:
        for name, content in members.items():
            data = content if isinstance(content, bytes) else content.encode()
            z.writestr(name, data)
    return path


CLEAN_SDIST = {
    "anonyfy-0.1.0/src/anonyfy/__init__.py": b'__version__ = "0.1.0"\n',
    "anonyfy-0.1.0/LICENSE": b"Apache-2.0\n",
    "anonyfy-0.1.0/README.md": b"# anonyfy\n",
}

CLEAN_WHEEL = {
    "anonyfy/__init__.py": b'__version__ = "0.1.0"\n',
    "anonyfy-0.1.0.dist-info/METADATA": b"Metadata-Version: 2.1\n",
}


def test_script_exists() -> None:
    """Le script check_distribution.py existe (rouge tant qu'il n'est pas créé)."""
    assert SCRIPT.is_file(), f"script manquant: {SCRIPT}"


def test_clean_sdist_returns_zero(tmp_path: Path) -> None:
    """Une sdist propre ne contient aucun fichier interdit -> exit 0."""
    sdist = _make_sdist(tmp_path / "anonyfy-0.1.0.tar.gz", CLEAN_SDIST)
    result = _run_script(sdist)
    assert result.returncode == 0, f"attendu 0, obtenu {result.returncode}: {result.stdout}{result.stderr}"


def test_clean_wheel_returns_zero(tmp_path: Path) -> None:
    """Une wheel propre ne contient aucun fichier interdit -> exit 0."""
    wheel = _make_wheel(tmp_path / "anonyfy-0.1.0-py3-none-any.whl", CLEAN_WHEEL)
    result = _run_script(wheel)
    assert result.returncode == 0, f"attendu 0, obtenu {result.returncode}: {result.stdout}{result.stderr}"


def test_sdist_with_bak_file_returns_one(tmp_path: Path) -> None:
    """Une sdist contenant un .bak -> exit 1."""
    members = dict(CLEAN_SDIST)
    members["anonyfy-0.1.0/src/anonyfy/vault.py.bak"] = b"old"
    sdist = _make_sdist(tmp_path / "anonyfy-0.1.0.tar.gz", members)
    result = _run_script(sdist)
    assert result.returncode == 1, f"attendu 1, obtenu {result.returncode}: {result.stdout}{result.stderr}"


def test_wheel_with_pycache_pyc_returns_one(tmp_path: Path) -> None:
    """Une wheel contenant __pycache__/*.pyc -> exit 1."""
    members = dict(CLEAN_WHEEL)
    members["anonyfy/__pycache__/vault.cpython-311.pyc"] = b"\x00\x00"
    wheel = _make_wheel(tmp_path / "anonyfy-0.1.0-py3-none-any.whl", members)
    result = _run_script(wheel)
    assert result.returncode == 1, f"attendu 1, obtenu {result.returncode}: {result.stdout}{result.stderr}"


def test_sdist_with_olgenius_dir_returns_one(tmp_path: Path) -> None:
    """Une sdist contenant .olgenius/ -> exit 1."""
    members = dict(CLEAN_SDIST)
    members["anonyfy-0.1.0/.olgenius/state.json"] = b"{}"
    sdist = _make_sdist(tmp_path / "anonyfy-0.1.0.tar.gz", members)
    result = _run_script(sdist)
    assert result.returncode == 1, f"attendu 1, obtenu {result.returncode}: {result.stdout}{result.stderr}"


def test_wheel_with_resume_md_returns_one(tmp_path: Path) -> None:
    """Une wheel contenant resume.md -> exit 1."""
    members = dict(CLEAN_WHEEL)
    members["anonyfy/resume.md"] = b"session"
    wheel = _make_wheel(tmp_path / "anonyfy-0.1.0-py3-none-any.whl", members)
    result = _run_script(wheel)
    assert result.returncode == 1, f"attendu 1, obtenu {result.returncode}: {result.stdout}{result.stderr}"


def test_sdist_with_corpus_real_returns_one(tmp_path: Path) -> None:
    """Une sdist contenant corpus_real/ -> exit 1."""
    members = dict(CLEAN_SDIST)
    members["anonyfy-0.1.0/tests/acceptance/corpus_real/doc_001.txt"] = b"secret"
    sdist = _make_sdist(tmp_path / "anonyfy-0.1.0.tar.gz", members)
    result = _run_script(sdist)
    assert result.returncode == 1, f"attendu 1, obtenu {result.returncode}: {result.stdout}{result.stderr}"


def test_sdist_with_gitignore_returns_one(tmp_path: Path) -> None:
    """Une sdist contenant .gitignore -> exit 1."""
    members = dict(CLEAN_SDIST)
    members["anonyfy-0.1.0/.gitignore"] = b"__pycache__/\n"
    sdist = _make_sdist(tmp_path / "anonyfy-0.1.0.tar.gz", members)
    result = _run_script(sdist)
    assert result.returncode == 1, f"attendu 1, obtenu {result.returncode}: {result.stdout}{result.stderr}"


def test_clean_sdist_and_wheel_together_return_zero(tmp_path: Path) -> None:
    """Plusieurs artefacts propres passés ensemble -> exit 0."""
    sdist = _make_sdist(tmp_path / "anonyfy-0.1.0.tar.gz", CLEAN_SDIST)
    wheel = _make_wheel(tmp_path / "anonyfy-0.1.0-py3-none-any.whl", CLEAN_WHEEL)
    result = _run_script(sdist, wheel)
    assert result.returncode == 0, f"attendu 0, obtenu {result.returncode}: {result.stdout}{result.stderr}"


def test_no_arguments_reports_usage() -> None:
    """Sans argument, le script affiche un message d'usage et quitte en erreur."""
    result = _run_script()
    assert result.returncode != 0
    assert result.stderr.strip() or result.stdout.strip(), "aucun message affiché pour l'absence d'argument"