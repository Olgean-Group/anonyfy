"""Tests phase 23: validation du scope à l'ouverture du registre (Q1).

Défense en profondeur: ``_check_or_migrate_schema`` lit ``meta.scope`` et
vérifie qu'il correspond au scope demandé. Sans ce check, ouvrir un DB
existaint avec un scope différent charge les entries (HMAC calculés avec
l'ancien scope) en mémoire tout en utilisant le nouveau scope pour les
nouvelles réservations -> invariant 2 (déterminisme scopé) cassé silencieusement.

Référence: PLAN.md phase 23, Q1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anonyfy.surrogate.registry import RegistryError, ScopeRegistry

_KEY = b"0" * 16


class TestScopeMismatch:
    def test_rouvrir_avec_scope_différent_lève_erreur(self, tmp_path: Path):
        path = str(tmp_path / "reg.db")
        r1 = ScopeRegistry(key=_KEY, scope="alpha", registry_path=path)
        r1.reserve("prenom", "Jean", gazetteer_size=50000)
        r1.close()
        # Rouvrir le MÊME fichier avec un scope différent doit échouer.
        with pytest.raises(RegistryError) as excinfo:
            ScopeRegistry(key=_KEY, scope="beta", registry_path=path)
        msg = str(excinfo.value).lower()
        assert "scope" in msg

    def test_rouvrir_avec_scope_correct_n_échoue_pas(self, tmp_path: Path):
        path = str(tmp_path / "reg.db")
        r1 = ScopeRegistry(key=_KEY, scope="alpha", registry_path=path)
        sub1 = r1.reserve("prenom", "Jean", gazetteer_size=50000)
        r1.close()
        # Rouvrir avec le même scope: pas d'erreur, déterminisme préservé.
        r2 = ScopeRegistry(key=_KEY, scope="alpha", registry_path=path)
        sub2 = r2.reserve("prenom", "Jean", gazetteer_size=50000)
        r2.close()
        assert sub1 == sub2

    def test_message_d_erreur_mentionne_les_deux_scopes(self, tmp_path: Path):
        path = str(tmp_path / "reg.db")
        r1 = ScopeRegistry(key=_KEY, scope="alpha", registry_path=path)
        r1.reserve("prenom", "Jean", gazetteer_size=50000)
        r1.close()
        with pytest.raises(RegistryError) as excinfo:
            ScopeRegistry(key=_KEY, scope="beta", registry_path=path)
        msg = str(excinfo.value)
        assert "alpha" in msg
        assert "beta" in msg
