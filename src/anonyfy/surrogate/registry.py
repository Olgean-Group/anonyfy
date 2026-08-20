"""Registre de scope SQLite persistant (phase 10).

Retient les indices/substituts déjà attribués pour garantir le déterminisme
scopé et l'injectivité (invariant 3), résout les collisions par sondage
linéaire déterministe (paradoxe des anniversaires, architecture §5.3), et
**ne stocke jamais de valeur claire** (invariant 1, D4, architecture §5.3).

Format: SQLite indexé via `sqlite3` stdlib (zéro dépendance, D4). Contenu
**non chiffré**: indices entiers dérivés via HMAC, substituts, empreinte HMAC.
La valeur claire n'est jamais persistée: le registre stocke uniquement
`clear_index` (entier = HMAC(key, scope||type||clair) mod gazetteer_size),
`clear_hmac` (HMAC-SHA256(key, clair), pour l'idempotence et l'audit) et le
`surrogate` (substitut déterministe scopé).

Caractéristiques (D4):
- `schema_version` en table `meta` + migration à l'ouverture + refus des
  schémas futurs inconnus.
- Écriture atomique (transaction SQLite par batch): une réservation est
  entièrement écrite ou absente (pas d'état partiel, OBJ-021). Les batches
  sont commités périodiquement (durabilité bornée) et à la fermeture.
- Verrou par scope (threading.Lock) sérialisant les réservations dans le
  processus, complément du verrouillage SQLite (OBJ-006).
- Sondage linéaire déterministe pour les collisions de substitut, via
  structures en mémoire (idempotence et sondage O(1)) rechargées depuis le
  disque à l'ouverture.
- Chemin de registre explicite (`registry_path`); défaut `~/.anonyfy/
  registries/<scope>.db` (utilisé par la CLI phase 16).

Performance: les lookups (idempotence par HMAC, sondage par substitut) sont
servis par des structures en mémoire (dict/set) rechargées à l'ouverture; les
INSERTs utilisent un rowid autoincrement séquentiel (pas de fragmentation du
B-tree sur substituts aléatoires); les commits sont batchés (un transaction
par batch de `_BATCH_SIZE` réservations) pour amortir le coût du fsync. La
latence sur 50 000 entrées est ainsi maintenue sous le seuil documenté (< 5 s).

Le registre se teste en isolation (fixture directe), sans Vault (phase 08).
`lookup(sub)->SurrogateRecord|None` est livré (phase 10b): il renvoie
l'enregistrement index/HMAC d'un substitut émis (appartenance), **pas la valeur
claire** (invariant 1). Le unmask clair est la responsabilité de la phase 08
(``fpe.decrypt`` pour FPE, registre+gazetteer pour petits domaines).

Référence: PLAN.md phase 10, DECISIONS.md D4, architecture §5.3.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "RegistryError",
    "SchemaVersionError",
    "ScopeRegistry",
    "SurrogateRecord",
    "default_registry_path",
]

# Version courante du schéma. Incrémenter en cas de changement de structure;
# l'ouverture migre les versions antérieures et refuse les versions futures.
CURRENT_SCHEMA_VERSION = 2

# Taille de batch: nombre de réservations par transaction commitée. Un batch
# est atomique (tout ou rien); un crash perd au plus le batch en cours (les
# réservations étant idempotentes, re-réserver reconstruit le même état).
_BATCH_SIZE = 1024


class RegistryError(Exception):
    """Erreur générique du registre de scope."""


class SchemaVersionError(RegistryError):
    """Le schéma du registre est plus récent que celui connu par cette version.

    Refus de charger un registre écrit par une version ultérieure (D4): on
    ne risque pas de corrompre des données dont on ne comprend pas le format.
    """


@dataclass(frozen=True, slots=True)
class SurrogateRecord:
    """Enregistrement d'un substitut émis (index/HMAC, **pas le clair**).

    Exposé par ``ScopeRegistry.lookup`` pour que l'automate (phase 10b) et
    l'arbitrage (phase 13) retrouvent un substitut sans jamais accéder à la
    valeur claire (invariant 1). Le unmask clair est la responsabilité de la
    phase 08 (``fpe.decrypt`` pour FPE, registre+gazetteer pour petits domaines).

    Attributes:
        surrogate: le substitut (surrogate) émis.
        entity_type: le type d'entité (ex. ``"prenom"``, ``"siret"``).
        clear_index: indice clair entier dérivé via HMAC (pas la valeur claire).
        clear_hmac: empreinte HMAC-SHA256 du clair (idempotence/audit, pas le clair).
    """

    surrogate: str
    entity_type: str
    clear_index: int
    clear_hmac: str
    case_pattern: str | None = None


class ScopeRegistry:
    """Registre de scope persistant (SQLite) pour les substituts scopés.

    Stocke `clear_index` (entier dérivé via HMAC), `surrogate` (substitut) et
    `clear_hmac` (empreinte HMAC du clair, pour idempotence/audit). Ne stocke
    jamais la valeur claire (invariant 1, D4).

    Thread-safe via un verrou par instance (sérialise les réservations dans le
    processus) combiné au verrouillage SQLite. Les lookups d'idempotence et de
    sondage sont servis en mémoire (rechargés depuis le disque à l'ouverture).
    """

    CURRENT_SCHEMA_VERSION = CURRENT_SCHEMA_VERSION

    def __init__(
        self,
        *,
        key: bytes,
        scope: str,
        registry_path: str,
    ) -> None:
        if not isinstance(key, (bytes, bytearray)):
            raise ValueError(f"clé attendue en bytes, reçu {type(key).__name__}")
        if len(key) not in (16, 24, 32):
            raise ValueError(f"longueur de clé {len(key)} invalide: 16, 24 ou 32 bytes")
        if not scope:
            raise ValueError("scope ne peut pas être vide")
        if not registry_path:
            raise ValueError("registry_path ne peut pas être vide")

        self._key = bytes(key)
        self._scope = scope
        self._registry_path = registry_path
        self._lock = threading.Lock()

        Path(registry_path).parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: autocommit; les transactions batch sont gérées
        # explicitement via BEGIN/COMMIT. check_same_thread=False: protégé par
        # self._lock.
        self._conn = sqlite3.connect(registry_path, isolation_level=None, check_same_thread=False)
        # DELETE + synchronous=OFF: atomicité par INSERT/batch (pas d'état
        # partiel) et vitesse. La durabilité sur coupure secteur est réduite
        # (perte au plus du batch en cours); acceptable car le registre ne
        # stocke pas de clair (invariant 1) et se reconstruit idempotent.
        self._conn.execute("PRAGMA journal_mode=DELETE")
        self._conn.execute("PRAGMA synchronous=OFF")

        # Structures en mémoire: idempotence (HMAC -> surrogate) et sondage
        # (ensemble des substituts déjà attribués). Rechargées depuis le disque.
        self._hmac_to_surrogate: dict[tuple[str, str], str] = {}
        self._used_surrogates: set[str] = set()
        # Compteur de réservations dans le batch en cours (pour le commit).
        self._pending = 0
        # Transaction batch en cours (ouverte par le premier INSERT du batch).
        self._txn_open = False

        self._init_schema()
        self._load_into_memory()

    # --- Propriétés ---------------------------------------------------------

    @property
    def registry_path(self) -> str:
        return self._registry_path

    @property
    def scope(self) -> str:
        return self._scope

    # --- Schéma / migration -------------------------------------------------

    def _init_schema(self) -> None:
        con = self._conn
        con.execute(
            "CREATE TABLE IF NOT EXISTS meta ("
            "  schema_version INTEGER NOT NULL,"
            "  scope TEXT NOT NULL"
            ")"
        )
        con.execute(
            "CREATE TABLE IF NOT EXISTS entries ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  surrogate TEXT NOT NULL,"
            "  entity_type TEXT NOT NULL,"
            "  clear_index INTEGER NOT NULL,"
            "  clear_hmac TEXT NOT NULL,"
            "  case_pattern TEXT"
            ")"
        )
        row = con.execute("SELECT COUNT(*) FROM meta").fetchone()
        if row[0] == 0:
            con.execute(
                "INSERT INTO meta(schema_version, scope) VALUES (?, ?)",
                (CURRENT_SCHEMA_VERSION, self._scope),
            )
        self._check_or_migrate_schema()

    def _check_or_migrate_schema(self) -> None:
        row = self._conn.execute("SELECT schema_version FROM meta").fetchone()
        if row is None:
            self._conn.execute(
                "INSERT INTO meta(schema_version, scope) VALUES (?, ?)",
                (CURRENT_SCHEMA_VERSION, self._scope),
            )
            return
        try:
            version = int(row[0])
        except (TypeError, ValueError) as exc:
            raise SchemaVersionError(f"schema_version illisible: {row[0]!r}") from exc
        if version > CURRENT_SCHEMA_VERSION:
            raise SchemaVersionError(
                f"schéma du registre (v{version}) plus récent que la version "
                f"connue (v{CURRENT_SCHEMA_VERSION}); refus de charger"
            )
        if version < CURRENT_SCHEMA_VERSION:
            self._migrate(version)
            self._conn.execute(
                "UPDATE meta SET schema_version=?",
                (CURRENT_SCHEMA_VERSION,),
            )

    def _migrate(self, from_version: int) -> None:
        # v1 -> v2: ajout colonne case_pattern (D24, flag casse types gazetteer).
        if from_version < 2:
            cols = {row[1] for row in self._conn.execute("PRAGMA table_info(entries)")}
            if "case_pattern" not in cols:
                self._conn.execute("ALTER TABLE entries ADD COLUMN case_pattern TEXT")

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT schema_version FROM meta").fetchone()
        if row is None:
            return CURRENT_SCHEMA_VERSION
        return int(row[0])

    def _load_into_memory(self) -> None:
        """Recharge les structures en mémoire depuis le disque (à l'ouverture).

        Permet aux lookups d'idempotence (HMAC -> surrogate) et de sondage
        (substituts déjà attribués) d'être O(1) en mémoire, sans index SQLite
        sur des colonnes à insertions aléatoires (qui fragmenteraient le B-tree).
        """
        for surrogate, entity_type, clear_hmac in self._conn.execute(
            "SELECT surrogate, entity_type, clear_hmac FROM entries"
        ):
            self._hmac_to_surrogate[(entity_type, clear_hmac)] = surrogate
            self._used_surrogates.add(surrogate)

    # --- Réservation --------------------------------------------------------

    def reserve(
        self,
        entity_type: str,
        clear_value: str,
        *,
        gazetteer_size: int,
    ) -> str:
        """Alloue (ou retrouve) un substitut déterministe scopé pour `clear_value`.

        Le substitut est déterministe (même (scope, type, clair, clé) -> même
        substitut) et injectif dans le scope (sondage linéaire borné sur les
        collisions). La valeur claire n'est jamais stockée: le registre persiste
        `clear_index` (entier HMAC mod gazetteer_size), `clear_hmac` (empreinte
        HMAC du clair) et le `surrogate`.

        Lève `RegistryError` si l'espace de substituts est saturé (sondage
        borné), `ValueError` si les arguments sont invalides.
        """
        if not entity_type:
            raise ValueError("entity_type ne peut pas être vide")
        if not clear_value:
            raise ValueError("clear_value ne peut pas être vide")
        if not isinstance(gazetteer_size, int) or isinstance(gazetteer_size, bool):
            raise ValueError(f"gazetteer_size doit être un entier, reçu {gazetteer_size!r}")
        if gazetteer_size <= 0:
            raise ValueError(f"gazetteer_size doit être > 0, reçu {gazetteer_size}")

        clear_hmac = self._hmac_clear(entity_type, clear_value)
        clear_index = self._clear_index(entity_type, clear_value, gazetteer_size)
        width = max(len(str(gazetteer_size - 1)) if gazetteer_size > 1 else 1, 6)

        with self._lock:
            # Idempotence: si ce clair est déjà enregistré, renvoyer son substitut.
            key = (entity_type, clear_hmac)
            existing = self._hmac_to_surrogate.get(key)
            if existing is not None:
                return existing

            # Sondage linéaire déterministe pour les collisions de substitut.
            probe = 0
            while probe < gazetteer_size:
                idx = (clear_index + probe) % gazetteer_size
                surrogate = f"{idx:0{width}d}"
                if surrogate not in self._used_surrogates:
                    # Emplacement libre: insérer (batch transactionnel) et
                    # enregistrer en mémoire.
                    self._insert(entity_type, surrogate, clear_index, clear_hmac)
                    self._hmac_to_surrogate[key] = surrogate
                    self._used_surrogates.add(surrogate)
                    return surrogate
                # Substitut pris par un autre clair: sonder la case suivante.
                probe += 1
            raise RegistryError(
                f"sondage linéaire saturé après {gazetteer_size} essais "
                f"(gazetteer_size={gazetteer_size}); espace de substituts épuisé"
            )

    def register_fpe(
        self,
        entity_type: str,
        clear_value: str,
        *,
        surrogate: str,
        case_pattern: str | None = None,
    ) -> str:
        """Enregistre un substitut FPE pré-calculé (grands domaines, phase 07/08).

        Contrairement à ``reserve`` (gazetteer: génère un substitut index), le
        substitut FPE est pré-calculé par FPE (phase 07) et fourni explicitement.
        Permet à ``unmask`` (phase 08) de vérifier l'appartenance du substitut au
        scope (invariant 4: ``contains`` / ``lookup``) et à l'automate Aho-Corasick
        (phase 10b) de retrouver le substitut via ``iter_surrogates``.

        ``case_pattern`` (D24): pattern casse par mot pour les types gazetteer
        (patronyme/prénom/commune/voie), permettant au unmask de restituer la casse
        originale depuis la forme majuscule du gazetteer. ``None`` pour les types
        sans casse (FPE). Ne contient pas le clair (invariant 1).

        Idempotent: un même (entity_type, clear_value) renvoie le substitut déjà
        enregistré. Lève ``RegistryError`` si le substitut est déjà attribué à un
        autre clair (collision inter-type, ne devrait pas arriver car FPE est
        bijectif par type et les types ont des formats distincts).
        """
        if not entity_type:
            raise ValueError("entity_type ne peut pas être vide")
        if not clear_value:
            raise ValueError("clear_value ne peut pas être vide")
        if not isinstance(surrogate, str) or not surrogate:
            raise ValueError("surrogate ne peut pas être vide")

        clear_hmac = self._hmac_clear(entity_type, clear_value)

        with self._lock:
            existing = self._hmac_to_surrogate.get((entity_type, clear_hmac))
            if existing is not None:
                return existing
            if surrogate in self._used_surrogates:
                raise RegistryError(
                    f"substitut FPE en collision avec un clair distinct: {surrogate!r}"
                )
            self._insert(entity_type, surrogate, 0, clear_hmac, case_pattern)
            self._hmac_to_surrogate[(entity_type, clear_hmac)] = surrogate
            self._used_surrogates.add(surrogate)
            return surrogate

    def _insert(
        self,
        entity_type: str,
        surrogate: str,
        clear_index: int,
        clear_hmac: str,
        case_pattern: str | None = None,
    ) -> None:
        """Insère une entrée via le batch transactionnel courant.

        Ouvre une transaction au premier INSERT du batch, commit tous les
        `_BATCH_SIZE` INSERTs. L'atomicité du batch garantit l'absence d'état
        partiel (D4/OBJ-021): un crash perd au plus le batch en cours, et les
        réservations étant idempotentes, re-réserver reconstruit le même état.
        """
        if not self._txn_open:
            self._conn.execute("BEGIN")
            self._txn_open = True
        self._conn.execute(
            "INSERT INTO entries(surrogate, entity_type, clear_index, clear_hmac, case_pattern) "
            "VALUES (?, ?, ?, ?, ?)",
            (surrogate, entity_type, clear_index, clear_hmac, case_pattern),
        )
        self._pending += 1
        if self._pending >= _BATCH_SIZE:
            self._conn.execute("COMMIT")
            self._txn_open = False
            self._pending = 0

    def flush(self) -> None:
        """Commit le batch en cours (durabilité immédiate)."""
        with self._lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if self._txn_open:
            self._conn.execute("COMMIT")
            self._txn_open = False
            self._pending = 0

    # --- Dérivations HMAC ---------------------------------------------------

    def _hmac_clear(self, entity_type: str, clear_value: str) -> str:
        """Empreinte HMAC-SHA-256(key, scope||entity_type||clear_value) hex.

        Sert d'identifiant stable du clair dans le scope (idempotence et audit,
        D3). Ne permet pas de remonter au clair sans la clé.
        """
        msg = (
            self._scope.encode("utf-8")
            + b"\x00"
            + entity_type.encode("utf-8")
            + b"\x00"
            + clear_value.encode("utf-8")
        )
        return hmac.new(self._key, msg, hashlib.sha256).hexdigest()

    def _clear_index(self, entity_type: str, clear_value: str, gazetteer_size: int) -> int:
        """Indice entier déterministe dans [0, gazetteer_size) pour le clair.

        Dérivé via HMAC(key, scope||type||clair) mod gazetteer_size. Déterminisme
        scopé (le scope et le type entrent dans le HMAC): deux clairs identiques
        dans deux scopes ou deux types donnent deux indices distincts.
        """
        msg = (
            self._scope.encode("utf-8")
            + b"\x00"
            + entity_type.encode("utf-8")
            + b"\x00"
            + clear_value.encode("utf-8")
        )
        digest = hmac.new(self._key, msg, hashlib.sha256).digest()
        return int.from_bytes(digest[:8], "big") % gazetteer_size

    # --- Recherche de substituts (phase 10b, invariant 1) -------------------

    def contains(self, surrogate: str) -> bool:
        """Indique si le substitut a été émis dans ce scope (appartenance).

        N'expose jamais le clair (invariant 1): répond uniquement oui/non sur le
        substitut. Servi en mémoire O(1) via l'ensemble des substituts attribués.
        """
        if not isinstance(surrogate, str):
            raise ValueError(f"surrogate attendu en str, reçu {type(surrogate).__name__}")
        with self._lock:
            return surrogate in self._used_surrogates

    def lookup(self, surrogate: str) -> SurrogateRecord | None:
        """Renvoie l'enregistrement d'un substitut émis, ou ``None`` s'il est inconnu.

        L'enregistrement expose ``surrogate``, ``entity_type``, ``clear_index``,
        ``clear_hmac`` (index/HMAC, **pas le clair**, invariant 1) et
        ``case_pattern`` (D24, pattern casse pour types gazetteer, ``None`` pour
        FPE). Le unmask clair est de la responsabilité de la phase 08.
        """
        if not isinstance(surrogate, str):
            raise ValueError(f"surrogate attendu en str, reçu {type(surrogate).__name__}")
        with self._lock:
            if surrogate not in self._used_surrogates:
                return None
            row = self._conn.execute(
                "SELECT surrogate, entity_type, clear_index, clear_hmac, case_pattern "
                "FROM entries WHERE surrogate=?",
                (surrogate,),
            ).fetchone()
        if row is None:
            return None
        return SurrogateRecord(
            surrogate=row[0],
            entity_type=row[1],
            clear_index=row[2],
            clear_hmac=row[3],
            case_pattern=row[4] if len(row) > 4 else None,
        )

    def iter_surrogates(self) -> Iterator[str]:
        """Énumère les substituts émis dans ce scope (pour ``AhoCorasick.from_registry``).

        N'expose jamais le clair (invariant 1): ne renvoie que les chaînes de
        substituts. Snapshot pris sous verrou puis itéré hors verrou.
        """
        with self._lock:
            snapshot = list(self._used_surrogates)
        yield from snapshot

    # --- Fermeture ----------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._flush_locked()
        try:
            self._conn.close()
        except Exception:
            pass


def default_registry_path(scope: str) -> str:
    """Chemin par défaut du registre pour un scope (`~/.anonyfy/registries/`).

    D4/PLAN phase 10: défaut `~/.anonyfy/registries/<scope>.db`. La CLI phase 16
    utilise ce défaut si `--registry` n'est pas fourni.
    """
    if not scope:
        raise ValueError("scope ne peut pas être vide")
    base = os.path.expanduser(os.path.join("~", ".anonyfy", "registries"))
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in scope)
    return os.path.join(base, f"{safe}.db")
