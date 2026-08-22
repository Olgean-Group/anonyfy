"""Tests du registre de scope SQLite (phase 10).

Valide: persistance SQLite, determinisme scopé, injectivité par sondage
linéaire, écriture atomique (crash), concurrence (verrou par scope),
rétro-compat schema_version, absence de clair stocké, latence 50k entrées.

Le registre stocke indice clair (entier dérivé via HMAC) + substitut +
empreinte HMAC, jamais la valeur claire (invariant 1, D4, architecture §5.3).
Testé en isolation (fixture directe), sans Vault (phase 08).

Référence: PLAN.md phase 10, D4, DECISIONS.md D4.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import tracemalloc
from pathlib import Path

import pytest

from anonyfy.surrogate.registry import RegistryError, SchemaVersionError, ScopeRegistry

ZERO_KEY = b"0" * 16
SCOPE = "dossier-47"


@pytest.fixture()
def registry_path(tmp_path: Path) -> str:
    return str(tmp_path / "reg.db")


@pytest.fixture()
def registry(registry_path: str) -> ScopeRegistry:
    r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
    yield r
    r.close()


# --- Construction / schéma --------------------------------------------------


class TestConstruction:
    def test_construction_cree_fichier_sqlite(self, registry_path: str):
        ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path).close()
        assert Path(registry_path).exists()

    def test_construction_rejette_cle_mauvaise_longueur(self, registry_path: str):
        with pytest.raises(ValueError):
            ScopeRegistry(key=b"0" * 8, scope=SCOPE, registry_path=registry_path)

    def test_construction_rejete_registry_path_vide(self):
        with pytest.raises(ValueError):
            ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path="")

    def test_meta_table_existe_apres_construction(self, registry: ScopeRegistry):
        con = sqlite3.connect(registry.registry_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            assert "meta" in tables
            assert "entries" in tables
        finally:
            con.close()


# --- Réserve basique --------------------------------------------------------


class TestReserveBasics:
    def test_reserve_renvoie_chaine(self, registry: ScopeRegistry):
        sub = registry.reserve("prenom", "Jean", gazetteer_size=50000)
        assert isinstance(sub, str)
        assert len(sub) > 0

    def test_reserve_substitut_différent_du_clair(self, registry: ScopeRegistry):
        sub = registry.reserve("prenom", "NomSecret", gazetteer_size=50000)
        assert sub != "NomSecret"
        assert "NomSecret" not in sub

    def test_reserve_gazetteer_size_obligatoire(self, registry: ScopeRegistry):
        with pytest.raises(TypeError):
            registry.reserve("prenom", "Jean")  # gazetteer_size manquant


# --- Déterminisme scopé -----------------------------------------------------


class TestDeterminism:
    def test_même_clair_même_substitut_même_instance(self, registry: ScopeRegistry):
        a = registry.reserve("prenom", "Jean", gazetteer_size=50000)
        b = registry.reserve("prenom", "Jean", gazetteer_size=50000)
        assert a == b

    def test_deux_clairs_distincts_substituts_distincts(self, registry: ScopeRegistry):
        a = registry.reserve("prenom", "Jean", gazetteer_size=50000)
        b = registry.reserve("prenom", "Marc", gazetteer_size=50000)
        assert a != b

    def test_déterminisme_rechargement_disque(self, registry_path: str):
        r1 = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        sub1 = r1.reserve("prenom", "Jean", gazetteer_size=50000)
        r1.close()
        # Recharger depuis le disque: même clair -> même substitut.
        r2 = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        sub2 = r2.reserve("prenom", "Jean", gazetteer_size=50000)
        r2.close()
        assert sub1 == sub2

    def test_déterminisme_clé_différente_substitut_différent(self, registry_path: str):
        r1 = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        a = r1.reserve("prenom", "Jean", gazetteer_size=50000)
        r1.close()
        Path(registry_path).unlink()
        r2 = ScopeRegistry(key=b"1" * 16, scope=SCOPE, registry_path=registry_path)
        b = r2.reserve("prenom", "Jean", gazetteer_size=50000)
        r2.close()
        assert a != b

    def test_scope_différent_substitut_différent(self, registry_path: str):
        ra = ScopeRegistry(key=ZERO_KEY, scope="A", registry_path=registry_path)
        a = ra.reserve("prenom", "Jean", gazetteer_size=50000)
        ra.close()
        Path(registry_path).unlink()
        rb = ScopeRegistry(key=ZERO_KEY, scope="B", registry_path=registry_path)
        b = rb.reserve("prenom", "Jean", gazetteer_size=50000)
        rb.close()
        assert a != b

    def test_idempotence_une_seule_entrée(self, registry: ScopeRegistry):
        registry.reserve("prenom", "Jean", gazetteer_size=50000)
        registry.reserve("prenom", "Jean", gazetteer_size=50000)
        # Flush pour rendre l'état commité visible d'une connexion externe
        # (les réservations sont batchées en transaction).
        registry.flush()
        con = sqlite3.connect(registry.registry_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM entries")
            assert cur.fetchone()[0] == 1
        finally:
            con.close()


# --- Injectivité / sondage linéaire ------------------------------------------


class TestInjectivité:
    def test_zéro_collision_5000_valeurs_distinctes(self, registry: ScopeRegistry):
        subs = set()
        for i in range(5000):
            subs.add(registry.reserve("prenom", f"nom{i}", gazetteer_size=50000))
        assert len(subs) == 5000

    def test_sondage_linéaire_résout_collision_index(self, registry: ScopeRegistry):
        # Deux clairs distincts forçant le même clear_index initial: le sondage
        # linéaire doit leur attribuer deux substituts distincts. On vérifie via
        # l'injectivité sur un gazetteer_size petit (1000) où les collisions sont
        # probables (paradoxe des anniversaires).
        subs = set()
        for i in range(800):
            subs.add(registry.reserve("prenom", f"nom{i}", gazetteer_size=1000))
        assert len(subs) == 800


# --- Absence de clair stocké (invariant 1) -----------------------------------


class TestPasDeClairStocké:
    def test_clair_absent_du_fichier_db(self, registry_path: str):
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        r.reserve("prenom", "NomSecret", gazetteer_size=50000)
        r.close()
        c = open(registry_path, "rb").read()
        assert b"NomSecret" not in c

    def test_clair_absent_des_colonnes(self, registry_path: str):
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        r.reserve("prenom", "NomSecret", gazetteer_size=50000)
        r.close()
        con = sqlite3.connect(registry_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT surrogate, entity_type, clear_index, clear_hmac FROM entries")
            for row in cur.fetchall():
                for col in row:
                    assert "NomSecret" not in str(col)
        finally:
            con.close()

    def test_aucune_colonne_texte_clair(self, registry: ScopeRegistry):
        con = sqlite3.connect(registry.registry_path)
        try:
            cur = con.cursor()
            cur.execute("PRAGMA table_info(entries)")
            cols = {row[1] for row in cur.fetchall()}
            # Aucune colonne ne porte un nom évoquant le clair stocké.
            assert "clear_value" not in cols
            assert "clear_text" not in cols
            assert "clear" not in cols
        finally:
            con.close()


# --- schema_version ----------------------------------------------------------


class TestSchemaVersion:
    def test_schema_version_présent_meta(self, registry: ScopeRegistry):
        con = sqlite3.connect(registry.registry_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT schema_version FROM meta")
            row = cur.fetchone()
            assert row is not None
            assert row[0] is not None
        finally:
            con.close()

    def test_schema_version_valeur_courante(self, registry: ScopeRegistry):
        assert registry.schema_version() == ScopeRegistry.CURRENT_SCHEMA_VERSION


# --- Rétro-compat schema_version --------------------------------------------


class TestRetrocompat:
    def test_lit_registre_schéma_antérieur(self, registry_path: str):
        # Écrire un registre avec le schéma courant, puis simuler un registre
        # écrit par une version antérieure (schema_version=0, même structure des
        # tables car le schéma v1 est un sur-ensemble). Le lecteur courant doit
        # le relire et migrer silencieusement.
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        sub = r.reserve("prenom", "Jean", gazetteer_size=50000)
        r.close()
        # Forger un schema_version antérieur (0 = pré-versionnage).
        con = sqlite3.connect(registry_path)
        try:
            con.execute("UPDATE meta SET schema_version=0")
            con.commit()
        finally:
            con.close()
        # Relire: l'entrée précédente reste accessible (réserve idempotente).
        r2 = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        sub2 = r2.reserve("prenom", "Jean", gazetteer_size=50000)
        assert sub == sub2
        assert r2.schema_version() == ScopeRegistry.CURRENT_SCHEMA_VERSION
        r2.close()

    def test_refuse_schéma_futur(self, registry_path: str):
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        r.reserve("prenom", "Jean", gazetteer_size=50000)
        r.close()
        con = sqlite3.connect(registry_path)
        try:
            future = ScopeRegistry.CURRENT_SCHEMA_VERSION + 1
            con.execute("UPDATE meta SET schema_version=?", (future,))
            con.commit()
        finally:
            con.close()
        with pytest.raises(SchemaVersionError):
            ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)


# --- Écriture atomique / crash -----------------------------------------------


class TestCrashAtomicité:
    def test_réservation_entièrement_écrite_ou_absente(self, registry: ScopeRegistry):
        # Une réservation aboutie est durable: rechargement retrouve le substitut.
        sub = registry.reserve("prenom", "Jean", gazetteer_size=50000)
        registry.close()
        r2 = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry.registry_path)
        sub2 = r2.reserve("prenom", "Jean", gazetteer_size=50000)
        r2.close()
        assert sub == sub2

    def test_crash_mi_transaction_pas_d_état_partiel(self, registry_path: str):
        # Simuler un crash: une connexion insère sans committer puis se ferme.
        # SQLite rollback l'entrée non commitée: pas d'état partiel lisible.
        # On crée d'abord le schéma via un registre (puis on le ferme pour
        # libérer le verrou d'écriture), puis on insère sans commit.
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        r.reserve("prenom", "Jean", gazetteer_size=50000)
        r.close()
        con = sqlite3.connect(registry_path)
        try:
            con.execute(
                "INSERT INTO entries(surrogate, entity_type, clear_index, clear_hmac) "
                "VALUES ('PARTIAL', 'prenom', 0, 'deadbeef')"
            )
            # NE PAS committer: fermer sans commit = rollback implicite.
        finally:
            con.close()
        # Le registre ne doit pas reconnaître l'entrée non commitée.
        r2 = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        con = sqlite3.connect(registry_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM entries WHERE surrogate='PARTIAL'")
            assert cur.fetchone()[0] == 0
            # L'entrée réservée (commitée avant close) est toujours là.
            cur.execute("SELECT COUNT(*) FROM entries")
            assert cur.fetchone()[0] == 1
        finally:
            con.close()
        r2.close()

    def test_commit_explicite_durable_apres_close(self, registry_path: str):
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        r.reserve("prenom", "Jean", gazetteer_size=50000)
        r.close()
        con = sqlite3.connect(registry_path)
        try:
            cur = con.cursor()
            cur.execute("SELECT COUNT(*) FROM entries")
            assert cur.fetchone()[0] == 1
        finally:
            con.close()


# --- Concurrence / verrou par scope ------------------------------------------


class TestConcurrency:
    def test_concurrence_injectivité_multithread(self, registry_path: str):
        # N threads x M réservations: aucun substitut partagé entre deux clairs.
        # Le verrou par scope sérialise; SQLite + transaction garantit l'intégrité.
        n_threads = 8
        m_reserves = 250
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        results: list[str] = []
        lock_results = threading.Lock()

        def worker(thread_id: int) -> None:
            local_subs: list[str] = []
            for j in range(m_reserves):
                clear = f"t{thread_id}-nom{j}"
                local_subs.append(r.reserve("prenom", clear, gazetteer_size=200000))
            with lock_results:
                results.extend(local_subs)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        r.close()
        assert len(results) == n_threads * m_reserves
        assert len(set(results)) == n_threads * m_reserves

    def test_concurrence_même_clair_même_substitut(self, registry_path: str):
        # Plusieurs threads réservant le MÊME clair: tous obtiennent le même
        # substitut (idempotence + verrou).
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        results: list[str] = []
        lock_results = threading.Lock()

        def worker() -> None:
            local = r.reserve("prenom", "Jean", gazetteer_size=50000)
            with lock_results:
                results.append(local)

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        r.close()
        assert len(set(results)) == 1


# --- Latence 50k -------------------------------------------------------------


class TestLatence:
    def test_latency_50k_sous_seuil(self, registry_path: str):
        # 50 000 réservations sous seuil documenté (< 5 s). gazetteer_size large
        # pour garder une faible charge (sondage linéaire rapide).
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        start = time.perf_counter()
        for i in range(50000):
            r.reserve("prenom", f"nom{i}", gazetteer_size=200000)
        elapsed = time.perf_counter() - start
        r.close()
        seuil = 5.0
        assert elapsed < seuil, f"latence 50k = {elapsed:.2f}s > {seuil}s"


# --- Cas limites -------------------------------------------------------------


class TestCasLimites:
    def test_type_différent_même_clair_substituts_différents(self, registry: ScopeRegistry):
        a = registry.reserve("prenom", "Jean", gazetteer_size=50000)
        b = registry.reserve("patronyme", "Jean", gazetteer_size=50000)
        assert a != b

    def test_gazetteer_size_un(self, registry: ScopeRegistry):
        # gazetteer_size=1: tous les clairs map vers l'unique index 0; le
        # sondage linéaire ne peut pas résoudre -> lève une exception bornée.
        registry.reserve("prenom", "Jean", gazetteer_size=1)
        with pytest.raises(RegistryError):
            # Deuxième clair distinct dans un espace de taille 1: collision
            # non résolvable.
            registry.reserve("prenom", "Marc", gazetteer_size=1)

    def test_reserve_type_vide_rejeté(self, registry: ScopeRegistry):
        with pytest.raises(ValueError):
            registry.reserve("", "Jean", gazetteer_size=50000)

    def test_reserve_clair_vide_rejeté(self, registry: ScopeRegistry):
        with pytest.raises(ValueError):
            registry.reserve("prenom", "", gazetteer_size=50000)

    def test_reserve_gazetteer_size_non_positif_rejeté(self, registry: ScopeRegistry):
        with pytest.raises(ValueError):
            registry.reserve("prenom", "Jean", gazetteer_size=0)


# --- OBJ-REC-103: check_gazetteer_version câblé au registre ------------------


class TestGazetteerVersionMismatch:
    """Phase 27 OBJ-REC-103: le registre persiste l'empreinte gazetteer en meta
    et lève GazetteerVersionMismatch à l'ouverture si l'empreinte stockée diffère
    de l'empreinte embarquée courante (garantie D5).

    Scénario: registre créé avec gazetteer version A → gazetteer mis à jour vers
    version B → réouverture → exception (les indices décalés cassent la
    réversibilité).
    """

    def test_gazetteer_version_mismatch_à_la_rouverture(self, registry_path: str):
        """Créer registre version A, changer l'empreinte stockée, rouvrir → exception."""
        from anonyfy.detect.gazetteers.loader import GazetteerVersionMismatch

        # 1. Créer le registre: persiste l'empreinte courante en meta.
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        r.close()

        # 2. Simuler une mise à jour du gazetteer: écraser l'empreinte stockée
        # par une empreinte différente (version A → version B).
        con = sqlite3.connect(registry_path)
        try:
            con.execute(
                "UPDATE meta SET gazetteer_version=?",
                ("empreinte_version_A_différente_du_tout",),
            )
            con.commit()
        finally:
            con.close()

        # 3. Rouvrir: l'empreinte stockée != empreinte embarquée → exception.
        with pytest.raises(GazetteerVersionMismatch):
            ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)

    def test_gazetteer_version_concordante_pas_dexception(self, registry_path: str):
        """Rouvrir un registre avec la même empreinte → pas d'exception."""
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        r.reserve("prenom", "Jean", gazetteer_size=50000)
        r.close()
        # Rouverture: l'empreinte n'a pas changé -> pas d'exception.
        r2 = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        r2.close()

    def test_gazetteer_version_persistée_en_meta(self, registry_path: str):
        """L'empreinte gazetteer est bien persistée dans la table meta à la création."""
        from anonyfy.detect.gazetteers.loader import gazetteer_version

        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
        r.close()
        con = sqlite3.connect(registry_path)
        try:
            row = con.execute("SELECT gazetteer_version FROM meta").fetchone()
            assert row is not None
            assert row[0] == gazetteer_version()
        finally:
            con.close()


# --- OBJ-REC-107: RAM Vault seul < 200 Mo (tracemalloc) ----------------------


class TestRamVault:
    """Phase 27 OBJ-REC-107: un Vault seul (avec lazy loading) consomme < 200 Mo
    en mémoire. Les gazetteers complets (1,3 M noms) ne sont chargés que si
    utilisés; le dict _pos est remplacé par tri + bisect (O(log n), zéro dict).
    """

    def test_ram_vault_seul_sous_200mo(self, tmp_path: Path):
        """Vault.__init__ froid: la mémoire allouée (tracemalloc) reste < 200 Mo."""
        from anonyfy import Vault

        tracemalloc.start()
        snap_before = tracemalloc.take_snapshot()
        try:
            v = Vault(key=ZERO_KEY, scope="ram-test", registry_path=str(tmp_path / "r.db"))
            snap_after = tracemalloc.take_snapshot()
            v.close()
        finally:
            tracemalloc.stop()
        # Calculer la différence de mémoire entre les deux snapshots.
        stat_before = snap_before.statistics("filename")
        stat_after = snap_after.statistics("filename")
        total_before = sum(s.size for s in stat_before)
        total_after = sum(s.size for s in stat_after)
        delta = total_after - total_before
        # < 200 Mo = 200 * 1024 * 1024 octets.
        seuil = 200 * 1024 * 1024
        mo = delta / 1024 / 1024
        assert delta < seuil, f"RAM Vault = {mo:.1f} Mo > {seuil / 1024 / 1024:.0f} Mo"
