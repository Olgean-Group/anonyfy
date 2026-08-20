"""Tests d'intégration Vault phase 13 (critères 1, 2, 3, 5, 6).

Texte d'intégration couvrant tous les types: patronyme, prénom, date, commune,
voie, SIRET, plaque, référence, email. Round-trip, pas de fuite, invariant 4,
monsieur_leroy (D7/OBJ-030).
"""

import pytest

from anonyfy import Vault

_KEY = b"0" * 16
_SCOPE = "s"


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


class TestCritere2RoundTrip:
    """Critère 2: round-trip sur texte d'intégration complet."""

    def test_round_trip_texte_integration(self, vault):
        t = (
            "M. Jean Dupont, né le 3 mai 1990, demeurant 12 rue de la Paix "
            "75001 Paris, SIRET 73282932000033"
        )
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_round_trip_texte_avec_email_plaque(self, vault):
        # D21: email régularisé (minuscule) pour round-trip exact (la régularisation
        # NFKC+minuscules est destructive; le casse-mixte est couvert par critère 9).
        t = "Contact: jean.o'brien@exemple.fr, plaque AB-123-CD, dossier DOS-123456"
        v = Vault(
            key=_KEY,
            scope=_SCOPE,
            registry_path=str(vault._registry.registry_path),
            reference_patterns=[r"DOS-\d{6}"],
        )
        m = v.mask(t)
        assert v.unmask(m.text) == t
        v.close()


class TestCritere3PasDeFuite:
    """Critère 3: aucune fuite du clair dans m.text."""

    def test_jean_dupont_absents(self, vault):
        t = "M. Jean Dupont"
        m = vault.mask(t)
        assert "Jean" not in m.text
        assert "Dupont" not in m.text

    def test_jean_absent_texte_integration(self, vault):
        t = "M. Jean Dupont, né le 3 mai 1990"
        m = vault.mask(t)
        assert "Jean" not in m.text
        assert "Dupont" not in m.text


class TestCritere5Invariant4:
    """Critère 5: un substitut non émis n'est jamais démasqué (invariant 4)."""

    def test_intrusion_substitut_inconnu(self, vault):
        t = "M. Jean Dupont"
        m = vault.mask(t)
        # Injecter un substitut intrus non enregistré
        intrusion = m.text + " Mr Intrusinconnu"
        result = vault.unmask(intrusion)
        # L'intrus reste tel quel (non démasqué)
        assert "Intrusinconnu" in result

    def test_intrusion_siret_inconnu(self, vault):
        vault.mask("SIRET 73282932000033")
        # Un SIRET non enregistré ne doit pas être démasqué
        result = vault.unmask("SIRET 11111111111111")
        assert "11111111111111" in result


class TestCritere6MonsieurLeroy:
    """D7/OBJ-030: mock modèle reformate, unmask restitue l'original.

    Le mock opère sur m.text (contient le substitut patronyme), produit
    "M. <substitut_nom>". unmask restitue "Marc Leroy" (texte clair original).
    Le clair n'apparaît que dans t et l'assertion ==t (invariant 1).
    """

    def test_monsieur_leroy(self, vault):
        t = "Marc Leroy"
        m = vault.mask(t)
        # Le substitut patronyme est dans m.text (pas le clair)
        assert "Marc" not in m.text
        assert "Leroy" not in m.text
        # Mock de modèle: reformate en "M. <substitut_nom>"
        # m.text contient le substitut (un autre patronyme du gazetteer)
        sub_nom = m.text.strip()  # m.text == substitut_nom
        reformate = f"M. {sub_nom}"
        # unmask restitue le texte clair original
        result = vault.unmask(reformate)
        assert result == f"M. {t}"
