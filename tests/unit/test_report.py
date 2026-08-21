"""Tests du rapport ``Vault.report()`` (phase 15).

Synthèse lisible par un non-développeur au format Markdown: types rencontrés,
volumes, règles actives, versions des gazetteers (PRD F10). Structure stable
pour diff (pas de timestamp variable).

Référence: PLAN.md phase 15, critères d'acceptation exécutables (4).
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import gazetteer_version


@pytest.fixture
def vault(tmp_path):
    reg = tmp_path / "reg.db"
    v = Vault(key=b"0" * 16, scope="s", registry_path=str(reg))
    yield v
    v.close()


class TestTypesVolumesGazetteer:
    """Critère 2 du PLAN: types + volumes + gazetteer présents."""

    def test_siret_nom_gazetteer_presents(self, vault):
        vault.mask("SIRET 73282932000033 et M. Jean Dupont")
        r = vault.report()
        assert "SIRET" in r
        assert "nom" in r.lower()
        assert "gazetteer" in r.lower()


class TestCompteSpans:
    """Critère 3 du PLAN: un compte apparaît dans le rapport."""

    def test_compte_siret_apparait(self, vault):
        vault.mask("SIRET 73282932000033")
        r = vault.report()
        # Le compte du type SIRET (>= 1) apparaît.
        assert "SIRET" in r
        # Au moins un chiffre de compte est présent.
        assert any(c.isdigit() for c in r)

    def test_zero_present_apres_un_mask(self, vault):
        """Critère 3 exact: '0' in report or 'zéro' in report.lower()."""
        vault.mask("SIRET 73282932000033")
        r = vault.report()
        assert "0" in r or "zéro" in r.lower()


class TestMarkdownStructure:
    """Le rapport est du Markdown structuré (titres, listes/table)."""

    def test_contient_titres_markdown(self, vault):
        vault.mask("SIRET 73282932000033")
        r = vault.report()
        assert "#" in r  # au moins un titre Markdown
        assert "\n" in r  # structuré multi-lignes


class TestVersionsGazetteers:
    """Le rapport contient la version des gazetteers (via gazetteer_version())."""

    def test_version_gazetteer_presente(self, vault):
        vault.mask("SIRET 73282932000033")
        r = vault.report()
        assert gazetteer_version() in r


class TestReportSansMasquage:
    """Report valide sans aucun mask (compte 0, types vides, gazetteer présent)."""

    def test_report_frais_sans_mask(self, vault):
        r = vault.report()
        assert "#" in r  # Markdown structuré
        assert "gazetteer" in r.lower()
        assert gazetteer_version() in r
        # Aucun type rencontré: la section types est vide ou absente.
        # Le compte total est 0.
        assert "0" in r  # compte 0 apparaît


class TestDeterminismeStabilite:
    """Deux reports sur le même Vault (même activité) → chaînes identiques."""

    def test_deux_reports_identiques(self, vault):
        vault.mask("SIRET 73282932000033 et M. Jean Dupont")
        r1 = vault.report()
        r2 = vault.report()
        assert r1 == r2

    def test_reports_apres_meme_activite_identiques(self, tmp_path):
        reg1 = tmp_path / "r1.db"
        reg2 = tmp_path / "r2.db"
        v1 = Vault(key=b"0" * 16, scope="s", registry_path=str(reg1))
        v2 = Vault(key=b"0" * 16, scope="s", registry_path=str(reg2))
        v1.mask("SIRET 73282932000033 et M. Jean Dupont")
        v2.mask("SIRET 73282932000033 et M. Jean Dupont")
        assert v1.report() == v2.report()
        v1.close()
        v2.close()


class TestPasDeFuite:
    """Invariant 1: le report ne fuit jamais de clair ni de substituts."""

    def test_pas_de_clair_dans_report(self, vault):
        vault.mask("SIRET 73282932000033 et M. Jean Dupont")
        r = vault.report()
        assert "73282932000033" not in r
        assert "Jean" not in r
        assert "Dupont" not in r

    def test_pas_de_substitut_dans_report(self, vault):
        m = vault.mask("SIRET 73282932000033 et M. Jean Dupont")
        r = vault.report()
        # Aucun substitut émis ne doit apparaître dans le report.
        for span in m.entities:
            sub = m.text[span.start : span.end]
            assert sub not in r
