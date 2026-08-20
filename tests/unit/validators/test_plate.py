"""Tests du validateur plaque SIV (phase 06).

Logique testée: validation du format SIV (AA-NNN-LL[L]) à la syntaxe près,
sans clé arithmétique. Mitigation des faux positifs: bornes et lettres/exclusions.
Confiance inférieure à 1.0 (format seul).
"""

from __future__ import annotations

from anonyfy.detect.validators.plate import detect, validate


class TestPlateValidate:
    def test_valide_format_ancien(self):
        # AA-123-CD: 2 lettres, 3 chiffres, 2 lettres.
        assert validate("AB-123-CD") is True

    def test_valide_format_nouveau_trois_lettres(self):
        # SIV étendu: 2 lettres, 3 chiffres, 3 lettres.
        assert validate("AB-123-CDE") is True

    def test_invalide_plan_phase13_valide(self):
        # Le critère phase 13 cite 'AB-123-CD' comme plaque valide.
        assert validate("AB-123-CD") is True

    def test_invalide_sans_tirets(self):
        assert validate("AB123CD") is False

    def test_invalide_chiffres_dans_lettres(self):
        assert validate("A1-123-CD") is False

    def test_invalide_trop_peu_de_chiffres(self):
        assert validate("AB-12-CD") is False

    def test_invalide_trop_de_chiffres(self):
        assert validate("AB-1234-CD") is False

    def test_invalide_minuscules(self):
        assert validate("ab-123-cd") is False

    def test_invalide_chaine_vide(self):
        assert validate("") is False

    def test_invalide_lettres_oui_conservant_ss(self):
        # Format structurellement valide mais contenant la séquence SS
        # historiquement exclue du SIV: la validation la rejette.
        assert validate("SS-123-AB") is False

    def test_invalide_lettres_iou_exclues(self):
        # I, O, U exclues du SIV (confusion avec 1, 0, V).
        assert validate("AI-123-CD") is False
        assert validate("AB-123-CO") is False


class TestPlateDetect:
    def test_detecte_plaque_dans_texte(self):
        spans = detect("plaque AB-123-CD du véhicule")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "AB-123-CD"
        assert s.type.value == "PLAQUE_SIV"
        assert s.start == 7
        assert s.end == 16
        assert s.confidence < 1.0

    def test_aucun_span_si_format_invalide(self):
        assert detect("ref AB123CD ici") == []

    def test_detecte_format_etendu(self):
        spans = detect("AA-001-ABC")
        assert len(spans) == 1
        assert spans[0].value == "AA-001-ABC"

    def test_detecte_plusieurs_plaques(self):
        spans = detect("AB-123-CD et AB-456-EF")
        assert len(spans) == 2
