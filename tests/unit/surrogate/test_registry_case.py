"""Tests D24: flag casse stocké dans le registre (pattern par mot).

Le registre persiste un pattern casse par mot (U/l/T) pour les types gazetteer,
permettant au unmask de restituer fidèlement la casse originale du clair depuis
la forme majuscule du gazetteer. Le pattern ne contient PAS le clair (invariant 1).

Schema v2: colonne ``case_pattern TEXT`` (nullable, NULL pour FPE sans casse).
Migration v1->v2: ALTER TABLE entries ADD COLUMN case_pattern TEXT.
"""

import sqlite3

from anonyfy.surrogate.case_pattern import apply_case, classify_case
from anonyfy.surrogate.registry import CURRENT_SCHEMA_VERSION, ScopeRegistry

_KEY = b"0" * 16


class TestClassifyCase:
    """classify_case retourne un pattern par mot (U/l/T)."""

    def test_uc(self):
        assert classify_case("MARC LEROY") == "U:U"

    def test_lc(self):
        assert classify_case("marc leroy") == "l:l"

    def test_tc(self):
        assert classify_case("Marc Leroy") == "T:T"

    def test_mx_rue_de_la_paix(self):
        assert classify_case("rue de la Paix") == "l:l:l:T"

    def test_mot_unique(self):
        assert classify_case("JEAN") == "U"
        assert classify_case("jean") == "l"
        assert classify_case("Jean") == "T"


class TestApplyCase:
    """apply_case restitue la casse depuis la forme majuscule du gazetteer."""

    def test_uc(self):
        assert apply_case("MARC LEROY", "U:U") == "MARC LEROY"

    def test_lc(self):
        assert apply_case("MARC LEROY", "l:l") == "marc leroy"

    def test_tc(self):
        assert apply_case("MARC LEROY", "T:T") == "Marc Leroy"

    def test_mx_rue_de_la_paix(self):
        assert apply_case("RUE DE LA PAIX", "l:l:l:T") == "rue de la Paix"

    def test_mot_unique(self):
        assert apply_case("JEAN", "U") == "JEAN"
        assert apply_case("JEAN", "l") == "jean"
        assert apply_case("JEAN", "T") == "Jean"


class TestRegisterCasePattern:
    """register_fpe stocke case_pattern; lookup l'expose."""

    def test_register_et_lookup_case_pattern(self, tmp_path):
        reg = ScopeRegistry(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        reg.register_fpe(
            "patronyme",
            "Marc Leroy",
            surrogate="CHARVET",
            case_pattern=classify_case("Marc Leroy"),
        )
        record = reg.lookup("CHARVET")
        assert record is not None
        assert record.case_pattern == "T:T"
        reg.close()

    def test_register_sans_case_pattern_null(self, tmp_path):
        reg = ScopeRegistry(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        reg.register_fpe("siret", "73282932000033", surrogate="11111111111111")
        record = reg.lookup("11111111111111")
        assert record is not None
        assert record.case_pattern is None
        reg.close()


class TestMigrationV1V2:
    """Migration schema v1 -> v2: ALTER TABLE + entrées préservées."""

    def test_migration_v1_v2(self, tmp_path):
        path = str(tmp_path / "r.db")
        # Créer un registre v1 manuellement (schema v1 sans case_pattern)
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE meta (schema_version INTEGER NOT NULL, scope TEXT NOT NULL)")
        con.execute(
            "CREATE TABLE entries ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  surrogate TEXT NOT NULL,"
            "  entity_type TEXT NOT NULL,"
            "  clear_index INTEGER NOT NULL,"
            "  clear_hmac TEXT NOT NULL"
            ")"
        )
        con.execute("INSERT INTO meta(schema_version, scope) VALUES (1, 's')")
        con.execute(
            "INSERT INTO entries(surrogate, entity_type, clear_index, clear_hmac) "
            "VALUES ('OLDSUB', 'siret', 0, 'oldhmac')"
        )
        con.commit()
        con.close()

        # Ouvrir avec le code v2: migration doit s'appliquer
        reg = ScopeRegistry(key=_KEY, scope="s", registry_path=path)
        assert reg.schema_version() == CURRENT_SCHEMA_VERSION
        # L'ancienne entrée est préservée, case_pattern NULL
        record = reg.lookup("OLDSUB")
        assert record is not None
        assert record.entity_type == "siret"
        assert record.case_pattern is None
        # La nouvelle colonne existe et accepte un case_pattern
        reg.register_fpe(
            "patronyme",
            "Marc Leroy",
            surrogate="CHARVET",
            case_pattern="T:T",
        )
        record2 = reg.lookup("CHARVET")
        assert record2.case_pattern == "T:T"
        reg.close()

    def test_schema_version_actuel_est_2(self):
        assert CURRENT_SCHEMA_VERSION == 2


class TestFlagNonClair:
    """Le pattern casse ne contient pas le clair (invariant 1)."""

    def test_pattern_ne_contient_pas_clair(self):
        pattern = classify_case("Marc Leroy")
        assert "Marc" not in pattern
        assert "Leroy" not in pattern
        # Le pattern ne contient que U/l/T et ':'
        assert all(c in "UlT:" for c in pattern)
