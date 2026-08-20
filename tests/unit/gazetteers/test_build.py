"""Tests du build de gazetteers (phase 09) - reproductibilite bit a bit.

Ces tests valident que scripts/build_gazetteers.py regenere les CSV gzippes
embarques de facon deterministe (gzip mtime fixe, lignes triees) et que --check
verifie l'identite bit a bit hors reseau.
"""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "scripts"
DATA = REPO / "src" / "anonyfy" / "detect" / "gazetteers" / "data"
RAW = DATA / "raw"


@pytest.fixture(scope="module")
def build_mod():
    """Importe scripts/build_gazetteers.py en tant que module."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        yield importlib.import_module("build_gazetteers")
    finally:
        sys.path.remove(str(SCRIPTS))
        sys.modules.pop("build_gazetteers", None)


def test_raw_sources_present():
    """Les sources brutes filtrees sont embarquees (reproductibilite hors reseau)."""
    for name in ("prenoms", "noms", "communes", "voies"):
        assert (RAW / f"{name}.csv").exists(), f"raw/{name}.csv manquant"


def test_build_deterministic(build_mod):
    """Deux builds produisent des octets identiques (meme contenu, mtime fixe)."""
    built1 = build_mod.build_all(DATA)
    built2 = build_mod.build_all(DATA)
    assert set(built1) == {"prenoms", "noms", "communes", "voies"}
    for name in built1:
        assert built1[name] == built2[name], f"{name} non deterministe"


def test_build_uses_gzip_with_fixed_mtime(build_mod):
    """Le gzip ne contient pas de mtime variable (header byte 4-7 = 0)."""
    built = build_mod.build_all(DATA)
    for name, blob in built.items():
        # mtime est aux octets 4-7 du header gzip (little-endian).
        assert blob[4:8] == b"\x00\x00\x00\x00", f"{name}: mtime gzip non fige"


def test_manifest_computes_version_and_sha256(build_mod):
    """Le manifest contient une empreinte version + un sha256 par gazetteer."""
    built = build_mod.build_all(DATA)
    manifest = build_mod.compute_manifest(DATA, built)
    assert isinstance(manifest["version"], str) and len(manifest["version"]) > 0
    for name in ("prenoms", "noms", "communes", "voies"):
        g = manifest["gazetteers"][name]
        assert len(g["sha256"]) == 64
        assert g["count"] > 0
        # le sha256 du blob correspond
        assert g["sha256"] == hashlib.sha256(built[name]).hexdigest()


def test_check_matches_committed(build_mod):
    """--check : le rebuild == l'embarque (fichiers committes)."""
    assert (DATA / "manifest.json").exists(), "manifest.json non committé"
    assert build_mod.check(DATA), (
        "le rebuild ne correspond pas aux csv.gz embarques (reproductibilite cassee)"
    )


def test_cli_check_exit_zero():
    """Critere 530: `python scripts/build_gazetteers.py --check` retourne 0."""
    import subprocess

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "build_gazetteers.py"), "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"--check non zero:\n{result.stdout}\n{result.stderr}"


def test_data_dir_under_20mb():
    """Critere 526: data/ < 20 Mo."""
    total = sum(f.stat().st_size for f in DATA.rglob("*") if f.is_file())
    assert total < 20 * 1024 * 1024, f"data/ = {total} octets >= 20 Mo"
