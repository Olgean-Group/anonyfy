"""Tests format_pattern du registre (phase 24, B1, OBJ-REC-101).

Valide: colonne format_pattern (schema_version 2->3), migration des registres
existants, stockage AVEC case_pattern (jamais le clair, invariant 1), et
restitution via lookup.

Référence: PLAN.md phase 24, OBJ-REC-101.
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from anonyfy.surrogate.registry import CURRENT_SCHEMA_VERSION, ScopeRegistry

ZERO_KEY = b"0" * 16
SCOPE = "dossier-24"


@pytest.fixture()
def registry_path(tmp_path: Path) -> str:
    return str(tmp_path / "reg.db")


@pytest.fixture()
def registry(registry_path: str) -> ScopeRegistry:
    r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=registry_path)
    yield r
    r.close()


class TestFormatPattern:
    def test_schema_version_est_3(self, registry: ScopeRegistry):
        assert registry.schema_version() == 3
        assert CURRENT_SCHEMA_VERSION == 3

    def test_colonne_format_pattern_existe(self, registry: ScopeRegistry):
        con = sqlite3.connect(registry.registry_path)
        try:
            cols = {row[1] for row in con.execute("PRAGMA table_info(entries)")}
        finally:
            con.close()
        assert "format_pattern" in cols

    def test_register_fpe_stocke_format_pattern(self, registry: ScopeRegistry):
        registry.register_fpe(
            "telephone",
            "0612345678",
            surrogate="0612345678",
            case_pattern=None,
            format_pattern="\x00 \x00",
        )
        rec = registry.lookup("0612345678")
        assert rec is not None
        assert rec.format_pattern == "\x00 \x00"

    def test_register_fpe_format_pattern_defaut_none(self, registry: ScopeRegistry):
        registry.register_fpe("siren", "123456789", surrogate="987654321")
        rec = registry.lookup("987654321")
        assert rec is not None
        assert rec.format_pattern is None

    def test_migration_v2_vers_v3_ajoute_colonne(self, tmp_path: Path):
        # Créer un registre v2 (sans format_pattern), puis migrer.
        path = str(tmp_path / "v2.db")
        con = sqlite3.connect(path)
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("PRAGMA synchronous=OFF")
        con.execute("CREATE TABLE meta (schema_version INTEGER NOT NULL, scope TEXT NOT NULL)")
        con.execute("INSERT INTO meta VALUES (2, ?)", (SCOPE,))
        con.execute(
            "CREATE TABLE entries ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "surrogate TEXT NOT NULL,"
            "entity_type TEXT NOT NULL,"
            "clear_index INTEGER NOT NULL,"
            "clear_hmac TEXT NOT NULL,"
            "case_pattern TEXT)"
        )
        con.execute(
            "INSERT INTO entries(surrogate, entity_type, clear_index, clear_hmac, case_pattern) "
            "VALUES ('AAA', 'siren', 0, 'h', 'L')"
        )
        con.commit()
        con.close()
        # Ouvrir avec ScopeRegistry: doit migrer vers v3.
        r = ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=path)
        try:
            assert r.schema_version() == 3
            con = sqlite3.connect(path)
            cols = {row[1] for row in con.execute("PRAGMA table_info(entries)")}
            assert "format_pattern" in cols
            # L'entrée préexistante a format_pattern NULL.
            row = con.execute("SELECT format_pattern FROM entries WHERE surrogate='AAA'").fetchone()
            assert row[0] is None
            con.close()
        finally:
            r.close()

    def test_format_pattern_ne_stocke_pas_le_clair(self, registry: ScopeRegistry):
        # Le template ne contient que des marqueurs et séparateurs, jamais le clair.
        tmpl = "\x00 \x00\x00 \x00\x00"
        registry.register_fpe(
            "telephone", "0612345678", surrogate="1111111111", format_pattern=tmpl
        )
        rec = registry.lookup("1111111111")
        assert rec is not None
        # Aucun chiffre du clair n'apparaît dans le template.
        for ch in rec.format_pattern or "":
            assert not ch.isdigit()

    def test_refuse_schema_futur_v4(self, tmp_path: Path):
        path = str(tmp_path / "v4.db")
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE meta (schema_version INTEGER NOT NULL, scope TEXT NOT NULL)")
        con.execute("INSERT INTO meta VALUES (4, ?)", (SCOPE,))
        con.execute("CREATE TABLE entries (surrogate TEXT)")
        con.commit()
        con.close()
        from anonyfy.surrogate.registry import SchemaVersionError

        with pytest.raises(SchemaVersionError):
            ScopeRegistry(key=ZERO_KEY, scope=SCOPE, registry_path=path)