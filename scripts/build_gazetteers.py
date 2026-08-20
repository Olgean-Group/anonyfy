#!/usr/bin/env python3
"""Build des gazetteers embarques (phase 09).

Regenere les CSV gzippes `data/{prenoms,noms,communes,voies}.csv.gz` depuis les
sources brutes filtrees `data/raw/*.csv` (snapshot embarque, hors reseau).

Reproductibilite bit a bit (critere 530):
  - lignes triees par cle deterministe (premiere colonne, casefold) ;
  - CSV UTF-8 sans BOM, separateur virgule, fin de ligne LF ;
  - gzip avec mtime figee a 0 (octets 4-7 du header = 0) ;
  - manifest.json avec sha256 par gazetteer + empreinte `version` globale.

Usage:
  python scripts/build_gazetteers.py          # ecrit data/*.csv.gz + manifest.json
  python scripts/build_gazetteers.py --check  # verifie rebuild == embarque, exit 0/1

Sources reelles (documentees dans docs/ADR/0001-fpe-ff3.md section 11):
  prenoms:   INSEE Fichier des prenoms, edition Juin 2022 (nat2021_csv.zip)
  noms:      Liste de patronymes extraite de SIRENE (INSEE), data.gouv.fr 14/10/2018
  communes:  INSEE Code Officiel Geographique (COG) 2026 (v_commune_2026.csv)
  voies:     Base Adresse Nationale (BAN), export par dept, snapshot 20/08/2026
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from io import StringIO
from pathlib import Path

GAZETTEERS = ("prenoms", "noms", "communes", "voies")

# Provenance des sources (figee dans l'ADR 0001 section 11).
SOURCES: dict[str, dict[str, str]] = {
    "prenoms": {
        "source": "INSEE - Fichier des prenoms, edition Juin 2022 (donnees 1900-2021)",
        "url": "https://www.insee.fr/fr/statistiques/fichier/2540004/nat2021_csv.zip",
    },
    "noms": {
        "source": "Liste de patronymes extraite de la base SIRENE (INSEE), data.gouv.fr 14/10/2018",
        "url": "https://static.data.gouv.fr/resources/liste-de-prenoms-et-patronymes/20181014-162921/patronymes.csv",
    },
    "communes": {
        "source": "INSEE - Code Officiel Geographique (COG) 2026",
        "url": "https://www.insee.fr/fr/statistiques/fichier/8740222/v_commune_2026.csv",
    },
    "voies": {
        "source": (
            "Base Adresse Nationale (BAN) - export adresses par dept, "
            "snapshot 20/08/2026 (05/15/23/48/90)"
        ),
        "url": "https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/",
    },
}


def _sort_key(row: list[str]) -> str:
    """Cle de tri deterministe: premiere colonne en casefold."""
    return (row[0] if row else "").casefold()


def _read_raw(data_dir: Path, name: str) -> tuple[list[str], list[list[str]]]:
    """Lit data/raw/{name}.csv -> (header, rows)."""
    path = data_dir / "raw" / f"{name}.csv"
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.reader(f)
        rows = list(r)
    if not rows:
        raise RuntimeError(f"raw/{name}.csv vide")
    return rows[0], rows[1:]


def _serialize(header: list[str], rows: list[list[str]]) -> bytes:
    """CSV UTF-8 sans BOM, separateur virgule, LF. Tri deterministe des lignes."""
    buf = StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for row in sorted(rows, key=_sort_key):
        w.writerow(row)
    return buf.getvalue().encode("utf-8")


def build_one(data_dir: Path, name: str) -> bytes:
    """Regenere le CSV gzippe pour un gazetteer (mtime figee a 0)."""
    header, rows = _read_raw(data_dir, name)
    payload = _serialize(header, rows)
    return gzip.compress(payload, compresslevel=9, mtime=0)


def build_all(data_dir: Path) -> dict[str, bytes]:
    """Regenere les 4 CSV gzippes en memoire."""
    return {name: build_one(data_dir, name) for name in GAZETTEERS}


def _count_rows(blob: bytes) -> int:
    """Nombre de lignes de donnees (hors header) d'un CSV gzippe."""
    text = gzip.decompress(blob).decode("utf-8")
    lines = text.splitlines()
    return max(len(lines) - 1, 0)


def compute_manifest(data_dir: Path, built: dict[str, bytes]) -> dict:
    """Calcule le manifest: sha256 par gazetteer + empreinte version globale.

    L'empreinte `version` est le sha256 de la concatenation (nom:sha256) triee,
    de sorte qu'elle change si le contenu d'un csv.gz change.
    """
    gazetteers: dict[str, dict] = {}
    for name in GAZETTEERS:
        digest = hashlib.sha256(built[name]).hexdigest()
        gazetteers[name] = {
            "source": SOURCES[name]["source"],
            "url": SOURCES[name]["url"],
            "sha256": digest,
            "count": _count_rows(built[name]),
        }
    concat = "|".join(f"{n}:{gazetteers[n]['sha256']}" for n in GAZETTEERS)
    version = hashlib.sha256(concat.encode("utf-8")).hexdigest()
    return {"version": version, "gazetteers": gazetteers}


def write_gazetteers(data_dir: Path) -> dict:
    """Build + ecriture des csv.gz et manifest.json sur disque."""
    built = build_all(data_dir)
    manifest = compute_manifest(data_dir, built)
    for name, blob in built.items():
        (data_dir / f"{name}.csv.gz").write_bytes(blob)
    manifest_text = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    (data_dir / "manifest.json").write_text(manifest_text, encoding="utf-8")
    return manifest


def check(data_dir: Path) -> bool:
    """Verifie que le rebuild == l'embarque (csv.gz + manifest). Hors reseau."""
    built = build_all(data_dir)
    manifest = compute_manifest(data_dir, built)
    for name, blob in built.items():
        committed = data_dir / f"{name}.csv.gz"
        if not committed.exists() or committed.read_bytes() != blob:
            return False
    committed_manifest = data_dir / "manifest.json"
    if not committed_manifest.exists():
        return False
    expected = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if committed_manifest.read_text(encoding="utf-8") != expected:
        return False
    return True


def main(argv: list[str]) -> int:
    repo = Path(__file__).resolve().parents[1]
    data_dir = repo / "src" / "anonyfy" / "detect" / "gazetteers" / "data"
    if "--check" in argv:
        if check(data_dir):
            print("OK: rebuild == embarque")
            return 0
        print("ECHEC: le rebuild differe des csv.gz embarques", file=sys.stderr)
        return 1
    manifest = write_gazetteers(data_dir)
    print(f"Build OK. version={manifest['version']}")
    for name in GAZETTEERS:
        g = manifest["gazetteers"][name]
        print(f"  {name}: {g['count']} entrees, sha256={g['sha256'][:12]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
