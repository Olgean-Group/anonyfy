#!/usr/bin/env python3
"""Garde-fou de distribution anonyfy (phase 22).

Inspecte le contenu des artefacts de ``dist/`` (sdist ``.tar.gz`` + wheel
``.whl``) et quitte avec code 1 si un fichier ou chemin interdit s'y trouve.

Fichiers/chemins interdits dans une distribution anonyfy (état local de
pilotage, sauvegardes, bytecode, corpus réel RGPD, sources gazetteers):

  - ``.olgenius/``      (état de pilotage Olgenius)
  - ``resume.md``       (mémoire de session)
  - ``*.bak``           (sauvegardes)
  - ``corpus_real/``    (corpus réel RGPD, jamais dans le dépôt)
  - ``__pycache__/``    (bytecode)
  - ``*.pyc``           (bytecode)
  - ``raw/``            (sources CSV gazetteers en clair, inutiles à l'exécution
                        — seuls les ``.csv.gz`` compressés de ``data/`` sont
                        embarqués; décision phase 31/M3, évite un doublon ~1 Mo)

``.gitignore`` est intentionnellement autorisé dans la sdist (standard PyPA,
hatchling ``force_include`` des fichiers d'exclusion VCS, inoffensif: patterns
d'ignorance seulement, aucune donnée sensible).

Usage::

    python scripts/check_distribution.py dist/*
    python scripts/check_distribution.py dist/anonyfy-0.1.0.tar.gz \\
        dist/anonyfy-0.1.0-py3-none-any.whl

Le script accepte un ou plusieurs chemins d'artefacts (la CI invoque
``dist/*``, le shell expansant en fichiers individuels). Il liste le contenu
de chaque archive et signale tout membre interdit.

Référence: whatsWire ``scripts/check_distribution.py`` (adapté à anonyfy).
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import tarfile
import zipfile
from pathlib import Path

# Motifs interdits. Les entrées terminées par ``/`` désignent un segment de
# répertoire; les entrées avec ``*`` sont des globs sur le nom de fichier; les
# autres sont des noms de fichier exacts (comparés au basename et en sous-chaîne).
FORBIDDEN: tuple[str, ...] = (
    ".olgenius/",
    "resume.md",
    "*.bak",
    "corpus_real/",
    "__pycache__/",
    "*.pyc",
    "raw/",
)


def _members(path: Path) -> list[str]:
    """Liste les membres d'une archive sdist (.tar.gz) ou wheel (.whl)."""
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.namelist()
    with tarfile.open(path) as archive:
        return archive.getnames()


def _is_forbidden(name: str) -> bool:
    """Indique si un membre d'archive correspond à un motif interdit."""
    parts = name.split("/")
    basename = parts[-1]
    for pattern in FORBIDDEN:
        if pattern.endswith("/"):
            segment = pattern[:-1]
            if segment in parts or pattern in name:
                return True
        elif "*" in pattern:
            if fnmatch.fnmatch(basename, pattern):
                return True
        else:
            if basename == pattern or pattern in name:
                return True
    return False


def main() -> int:
    """Point d'entrée: inspecte chaque artefact et signale les membres interdits."""
    parser = argparse.ArgumentParser(
        description="Vérifie qu'aucun fichier interdit n'est présent dans les distributions.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="chemins d'artefacts à inspecter (ex. dist/*).",
    )
    args = parser.parse_args()

    bad: list[str] = []
    for raw in args.paths:
        path = Path(raw)
        if not path.is_file():
            print(f"erreur: artefact introuvable: {path}", file=sys.stderr)
            return 2
        for name in _members(path):
            if _is_forbidden(name):
                bad.append(f"{path.name}: {name}")

    if bad:
        print("membres interdits dans la distribution:", *bad, sep="\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
