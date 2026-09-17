"""Phase 65 — LOGGING-REPLI-GENRE, ASSERTION-INTRUSION-FAIBLE, docstrings.

Trois constats MINEUR de revues antérieures :

- ``LOGGING-REPLI-GENRE`` : ``pick`` replie silencieusement sur le gazetteer
  complet quand le genre demandé n'existe pas. Le PLAN prévoyait « repli sur
  genre neutre + avertissement journalisé ». L'avertissement manquait.
- ``ASSERTION-INTRUSION-FAIBLE`` : l'assertion
  ``"..." not in result or result == "..."`` est tautologique (elle passe même
  si l'invariant 4 est violé).
- ``DOCSTRING-*`` : deux docstrings périmées, déjà corrigées ; test de garde.

Référence: BACKLOG LOGGING-REPLI-GENRE, ASSERTION-INTRUSION-FAIBLE.
"""

from __future__ import annotations

import warnings

import pytest

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import load_prenoms

KEY = b"0" * 16


class TestRepliGenreAverti:
    """Le repli sur genre neutre émet un avertissement explicite."""

    def test_repli_genre_averti(self):
        from anonyfy.surrogate.gazetteer import pick

        # Genre absent du gazetteer : aucune entrée ne porte ce genre.
        gazetteer = load_prenoms()
        with pytest.warns(UserWarning, match="repli|genre"):
            result = pick(
                entity_type="prenom",
                clear_value="Jean",
                scope="s",
                key=KEY,
                gazetteer=gazetteer,
                gender="XX",
            )
        assert result.name, "le repli doit tout de même rendre un substitut"

    def test_resultat_expose_le_repli(self):
        from anonyfy.surrogate.gazetteer import pick

        result = pick(
            entity_type="prenom",
            clear_value="Jean",
            scope="s",
            key=KEY,
            gazetteer=load_prenoms(),
            gender="XX",
        )
        assert result.gender_fallback is True, (
            "le résultat doit signaler que le genre n'a pas été préservé"
        )

    def test_genre_valide_sans_avertissement(self):
        from anonyfy.surrogate.gazetteer import pick

        with warnings.catch_warnings():
            warnings.simplefilter("error")  # tout avertissement devient une erreur
            result = pick(
                entity_type="prenom",
                clear_value="Jean",
                scope="s",
                key=KEY,
                gazetteer=load_prenoms(),
                gender="M",
            )
        assert result.gender_fallback is False
        assert result.gender == "M"

    def test_sans_genre_demande_pas_de_repli(self):
        from anonyfy.surrogate.gazetteer import pick

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = pick(
                entity_type="prenom",
                clear_value="Jean",
                scope="s",
                key=KEY,
                gazetteer=load_prenoms(),
            )
        assert result.gender_fallback is False

    def test_avertissement_sans_fuite_de_clair(self):
        """L'avertissement ne doit jamais contenir la valeur claire (invariant 1)."""
        from anonyfy.surrogate.gazetteer import pick

        clair = "Jean-Baptiste"
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            pick(
                entity_type="prenom",
                clear_value=clair,
                scope="s",
                key=KEY,
                gazetteer=load_prenoms(),
                gender="XX",
            )
        assert captured, "un avertissement était attendu"
        for warning in captured:
            assert clair not in str(warning.message), (
                f"fuite du clair dans l'avertissement: {warning.message}"
            )


class TestAssertionIntrusionDurcie:
    """L'assertion de l'invariant 4 est stricte (plus de tautologie)."""

    def test_assertion_est_stricte_dans_le_fichier(self):
        from pathlib import Path

        path = Path(__file__).parents[1] / "unit" / "test_vault_structured.py"
        texte = path.read_text(encoding="utf-8")
        # L'assertion tautologique ne doit plus apparaître comme CODE (elle peut
        # être citée dans la docstring qui documente le durcissement).
        lignes_code = [ligne for ligne in texte.splitlines() if ligne.strip().startswith("assert ")]
        suspectes = [ligne for ligne in lignes_code if " or result ==" in ligne]
        assert not suspectes, f"assertion tautologique résiduelle: {suspectes}"

    def test_invariant4_strict_bout_en_bout(self, tmp_path):
        """Un SIRET Luhn-valide jamais émis n'est pas déchiffré (strict)."""
        v = Vault(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        try:
            result = v.unmask("SIRET 41804261100008")
            assert result == "SIRET 41804261100008", (
                f"invariant 4 violé: {result!r} (le SIRET n'a jamais été masqué)"
            )
        finally:
            v.close()

    def test_invariant4_apres_un_autre_mask(self, tmp_path):
        v = Vault(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        try:
            v.mask("SIRET 73282932000033")
            result = v.unmask("SIRET 41804261100008")
            assert result == "SIRET 41804261100008"
        finally:
            v.close()


class TestDocstringsAJour:
    """Les docstrings signalées périmées ne le sont plus (gardes)."""

    def test_registry_docstring_ne_dit_pas_lookup_absent(self):
        from pathlib import Path

        texte = (Path("src") / "anonyfy" / "surrogate" / "registry.py").read_text(encoding="utf-8")
        assert "lookup n'est pas livré ici" not in texte

    def test_checkdist_test_docstring_ne_liste_pas_gitignore_interdit(self):
        from pathlib import Path

        texte = (Path("tests") / "unit" / "test_check_distribution.py").read_text(encoding="utf-8")
        # La section des interdits ne doit plus mentionner .gitignore.
        entete = texte.split("def ", 1)[0]
        assert "``.gitignore``" not in entete or "autorisé" in entete
