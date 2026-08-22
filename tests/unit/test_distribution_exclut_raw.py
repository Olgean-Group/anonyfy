"""Phase 31 (M3): la distribution n'embarque pas data/raw/.

Les gazetteers sources en clair (``data/raw/*.csv``) sont inutiles à
l'exécution: seuls les ``.csv.gz`` compressés de ``data/`` sont chargés.
Embarquer ``raw/`` double la taille (~1 Mo) et expose les sources en clair.

Cette phase valide deux garde-fous:

1. **Config hatchling** (``pyproject.toml``): un ``exclude`` ciblant
   ``src/anonyfy/detect/gazetteers/data/raw`` doit empêcher l'inclusion de
   ``raw/`` dans le wheel ET la sdist. On valide la présence de cette
   exclusion via ``tomllib`` (test rapide, sans build).

2. **Script ``check_distribution.py``**: le motif ``raw/`` doit figurer
   parmi les chemins interdits, afin qu'une régression de packaging soit
   détectée en CI. On valide qu'une archive contenant ``raw/`` est rejetée
   (exit 1) via le même sous-processus que les autres motifs interdits.
"""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_distribution.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"

RAW_REL = "src/anonyfy/detect/gazetteers/data/raw"


def _run_script(*paths: Path) -> subprocess.CompletedProcess[str]:
    """Invoque check_distribution.py en sous-processus."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(p) for p in paths)],
        capture_output=True,
        text=True,
        check=False,
    )


def _make_wheel(path: Path, members: dict[str, bytes]) -> Path:
    """Construit une wheel .whl (zip) avec les membres donnés."""
    with zipfile.ZipFile(path, "w") as z:
        for name, content in members.items():
            z.writestr(name, content)
    return path


def _make_sdist(path: Path, members: dict[str, bytes]) -> Path:
    """Construit une sdist .tar.gz avec les membres donnés."""
    with tarfile.open(path, "w:gz") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name=name)
            data = content if isinstance(content, bytes) else content.encode()
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def test_pyproject_excludes_raw_from_builds() -> None:
    """pyproject.toml déclare une exclusion hatchling ciblant raw/."""
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    hatch = config["tool"]["hatch"]
    # L'exclusion globale sous [tool.hatch.build] s'applique au wheel ET à la
    # sdist. On accepte aussi une exclusion par cible, tant que raw/ y figure.
    excludes: list[str] = []
    build = hatch.get("build", {})
    excludes += build.get("exclude", [])
    for target in ("wheel", "sdist"):
        tgt = hatch.get("build", {}).get("targets", {}).get(target, {})
        excludes += tgt.get("exclude", [])
    assert any("raw" in entry for entry in excludes), (
        f"aucune exclusion hatchling ne cible raw/: {excludes!r}"
    )


def test_pyproject_raw_path_is_real_directory() -> None:
    """Le chemin brut exclu dans pyproject.toml pointe vers un dossier existant.

    Garde-fou contre une faute de frappe dans l'exclusion (ex. un chemin
    inexistant n'exclurait rien mais passerait le test de chaîne).
    """
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    hatch = config["tool"]["hatch"]
    excludes: list[str] = []
    build = hatch.get("build", {})
    excludes += build.get("exclude", [])
    for target in ("wheel", "sdist"):
        tgt = hatch.get("build", {}).get("targets", {}).get(target, {})
        excludes += tgt.get("exclude", [])
    raw_entries = [e for e in excludes if "raw" in e]
    assert raw_entries, f"aucune exclusion raw/ dans pyproject.toml: {excludes!r}"
    # Au moins une entrée correspond à un répertoire réel du dépôt.
    assert any((REPO_ROOT / e).is_dir() for e in raw_entries), (
        f"l'exclusion raw/ ne pointe vers aucun répertoire existant: {raw_entries!r}"
    )


def test_check_distribution_rejects_raw_in_wheel(tmp_path: Path) -> None:
    """Une wheel contenant data/raw/ doit être rejetée (exit 1)."""
    members = {
        "anonyfy/__init__.py": b'__version__ = "0.1.0"\n',
        "anonyfy-0.1.0.dist-info/METADATA": b"Metadata-Version: 2.1\n",
        "anonyfy/detect/gazetteers/data/raw/noms.csv": b"nom\nDUPONT\n",
    }
    wheel = _make_wheel(tmp_path / "anonyfy-0.1.0-py3-none-any.whl", members)
    result = _run_script(wheel)
    assert result.returncode == 1, (
        f"raw/ devrait être interdit dans la wheel: {result.stdout}{result.stderr}"
    )


def test_check_distribution_rejects_raw_in_sdist(tmp_path: Path) -> None:
    """Une sdist contenant data/raw/ doit être rejetée (exit 1)."""
    members = {
        "anonyfy-0.1.0/src/anonyfy/__init__.py": b'__version__ = "0.1.0"\n',
        "anonyfy-0.1.0/src/anonyfy/detect/gazetteers/data/raw/noms.csv": b"nom\nDUPONT\n",
    }
    sdist = _make_sdist(tmp_path / "anonyfy-0.1.0.tar.gz", members)
    result = _run_script(sdist)
    assert result.returncode == 1, (
        f"raw/ devrait être interdit dans la sdist: {result.stdout}{result.stderr}"
    )


def test_check_distribution_allows_gzipped_gazetteers(tmp_path: Path) -> None:
    """Les .csv.gz compressés (hors raw/) restent autorisés: seuls raw/ est exclu."""
    members = {
        "anonyfy/__init__.py": b'__version__ = "0.1.0"\n',
        "anonyfy-0.1.0.dist-info/METADATA": b"Metadata-Version: 2.1\n",
        "anonyfy/detect/gazetteers/data/noms.csv.gz": b"\x1f\x8b\x08\x00",
    }
    wheel = _make_wheel(tmp_path / "anonyfy-0.1.0-py3-none-any.whl", members)
    result = _run_script(wheel)
    assert result.returncode == 0, (
        f"les .csv.gz ne doivent pas être interdits: {result.stdout}{result.stderr}"
    )
