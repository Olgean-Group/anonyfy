"""Chargeur paresseux des gazetteers embarques (phase 09).

Les gazetteers (prenoms, noms/patronymes, communes, voies) sont embarques en CSV
gzippé dans ``data/`` et chargés en mémoire au premier appel (chargement paresseux).
L'index est insensible à la casse (casefold). Chaque entrée porte des attributs:
  - prenoms:   ``genre`` (M / F / MF)
  - communes:  ``departement`` (code département INSEE)
  - noms:      ``count`` (nombre d'occurrences)
  - voies:     nom uniquement

Empreinte de version (D5, OBJ-003): ``gazetteer_version()`` retourne l'empreinte
figée du gazetteer embarqué (sha256 du manifest). Au ``unmask``, le registre
(phase 10) persiste cette empreinte et appelle ``check_gazetteer_version()`` qui
lève ``GazetteerVersionMismatch`` si l'empreinte stockée diffère de l'embarquée
(une mise à jour du gazetteer casserait la réversibilité des registres persistés).

Référence: PLAN.md phase 09, ADR 0001 section 11.
"""

from __future__ import annotations

import csv
import dataclasses
import gzip
import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "data"


class GazetteerVersionMismatch(Exception):
    """L'empreinte de version du gazetteer stockée diffère de l'embarquée.

    Levée au ``unmask`` quand le gazetteer embarqué a changé depuis le ``mask``
    (les indices décalés cassent la réversibilité des registres persistés).
    """


@dataclasses.dataclass(frozen=True)
class GazetteerEntry:
    """Entrée d'un gazetteer avec attributs optionnels selon le type.

    ``genre`` pour les prénoms, ``departement`` pour les communes, ``count``
    pour les patronymes. Les attributs non pertinents restent à leur valeur par
    défaut (chaîne vide / 0).
    """

    name: str
    genre: str = ""
    departement: str = ""
    count: int = 0


class Gazetteer:
    """Index insensible à la casse d'entrées de gazetteer.

    ``'Jean' in g``, ``len(g)``, ``g['Jean']`` ( KeyError si absent ),
    itération sur les entrées. La clé de recherche est normalisée par casefold.
    """

    def __init__(self, entries: dict[str, GazetteerEntry]) -> None:
        self._index = entries

    def __contains__(self, key: str) -> bool:
        return key.casefold() in self._index

    def __getitem__(self, key: str) -> GazetteerEntry:
        return self._index[key.casefold()]

    def __len__(self) -> int:
        return len(self._index)

    def __iter__(self):
        return iter(self._index.values())


# --- chargement paresseux avec cache en mémoire ---

_CACHE: dict[str, Gazetteer] = {}
_VERSION: str | None = None


def reset_cache() -> None:
    """Invalide le cache paresseux (tests / rechargement explicite)."""
    global _VERSION
    _CACHE.clear()
    _VERSION = None


def _read_csv_gz(name: str) -> tuple[list[str], list[list[str]]]:
    """Lit data/{name}.csv.gz -> (header, rows)."""
    path = _DATA_DIR / f"{name}.csv.gz"
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        raise RuntimeError(f"{path} vide")
    return rows[0], rows[1:]


def _build_index(name: str, make_entry) -> Gazetteer:
    """Construit l'index casefold -> entry à partir du CSV gzippé.

    En cas de clé dupliquée (noms de communes partagés), la première occurrence
    selon l'ordre du fichier l'emporte (le CSV embarqué est trié par code commune).
    """
    header, rows = _read_csv_gz(name)
    col = {c: i for i, c in enumerate(header)}
    index: dict[str, GazetteerEntry] = {}
    for row in rows:
        entry = make_entry(col, row)
        key = entry.name.casefold()
        if key and key not in index:
            index[key] = entry
    return Gazetteer(index)


def load_prenoms() -> Gazetteer:
    """Gazetteer des prénoms (INSEE Fichier des prénoms, édition Juin 2022)."""
    if "prenoms" not in _CACHE:

        def make(col, row):
            return GazetteerEntry(
                name=row[col["prenom"]].strip(),
                genre=row[col["genre"]].strip(),
                count=int(row[col["count"]]) if row[col["count"]].strip() else 0,
            )

        _CACHE["prenoms"] = _build_index("prenoms", make)
    return _CACHE["prenoms"]


def load_noms() -> Gazetteer:
    """Gazetteer des patronymes (extrait SIRENE INSEE, data.gouv.fr 14/10/2018)."""
    if "noms" not in _CACHE:

        def make(col, row):
            return GazetteerEntry(
                name=row[col["patronyme"]].strip(),
                count=int(row[col["count"]]) if row[col["count"]].strip() else 0,
            )

        _CACHE["noms"] = _build_index("noms", make)
    return _CACHE["noms"]


def load_communes() -> Gazetteer:
    """Gazetteer des communes (INSEE COG 2026) avec attribut département."""
    if "communes" not in _CACHE:

        def make(col, row):
            return GazetteerEntry(
                name=row[col["nom"]].strip(),
                departement=row[col["departement"]].strip(),
            )

        _CACHE["communes"] = _build_index("communes", make)
    return _CACHE["communes"]


def load_voies() -> Gazetteer:
    """Gazetteer des voies (Base Adresse Nationale, snapshot 20/08/2026)."""
    if "voies" not in _CACHE:

        def make(col, row):
            return GazetteerEntry(name=row[col["nom_voie"]].strip())

        _CACHE["voies"] = _build_index("voies", make)
    return _CACHE["voies"]


# --- empreinte de version figée (D5) ---


def _load_manifest() -> dict:
    path = _DATA_DIR / "manifest.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def gazetteer_version() -> str:
    """Empreinte de version figée du gazetteer embarqué (critère 528).

    sha256 globale sur l'ensemble des csv.gz embarqués (voir manifest.json).
    Le registre (phase 10) persiste cette empreinte au ``mask`` et la vérifie au
    ``unmask`` via ``check_gazetteer_version``.
    """
    global _VERSION
    if _VERSION is None:
        _VERSION = _load_manifest()["version"]
    return _VERSION


def check_gazetteer_version(stored: str) -> None:
    """Lève ``GazetteerVersionMismatch`` si ``stored`` != empreinte embarquée.

    Appelée au ``unmask``: une mise à jour du gazetteer entre le ``mask`` et le
    ``unmask`` casserait la réversibilité (les indices décalés), d'où le rejet.
    """
    current = gazetteer_version()
    if stored != current:
        raise GazetteerVersionMismatch(
            f"empreinte gazetteer stockée {stored!r} != embarquée {current!r}"
        )


__all__ = [
    "Gazetteer",
    "GazetteerEntry",
    "GazetteerVersionMismatch",
    "check_gazetteer_version",
    "gazetteer_version",
    "load_communes",
    "load_noms",
    "load_prenoms",
    "load_voies",
    "reset_cache",
]
