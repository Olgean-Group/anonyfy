"""Tests du validateur téléphone FR (phase 06).

Logique testée: validation du format du plan de numérotation français:
  - 10 chiffres commençant par 0 + chiffre valide FR (0[1-9]\\d{8});
  - +33 suivi de 9 chiffres (\\+33[1-9]\\d{8}).
Pas de clé de contrôle arithmétique: la confiance est inférieure à 1.0.
Mitigation des faux positifs (risque PLAN "tout numéro à 10 chiffres"):
un numéro ne commençant ni par 0+[1-9] ni par +33[1-9] est rejeté.
"""

from __future__ import annotations

from anonyfy.detect.validators.phone import detect, validate


class TestPhoneValidate:
    def test_valide_plan_international(self):
        assert validate("+33612345678") is True

    def test_valide_plan_national(self):
        assert validate("0612345678") is True

    def test_invalide_plan_sans_prefixe(self):
        # 10 chiffres mais ne commence pas par 0 (risque PLAN).
        assert validate("1234567890") is False

    def test_invalide_zero_puis_zero(self):
        # 0 suivi de 0: hors plan FR.
        assert validate("0012345678") is False

    def test_invalide_trop_court(self):
        assert validate("061234567") is False

    def test_invalide_trop_long(self):
        assert validate("06123456789") is False

    def test_invalide_lettres(self):
        assert validate("0612AB45678") is False

    def test_invalide_plus33_sans_chiffre_valide(self):
        # +33 0...: le 0 initial est supprimé en international.
        assert validate("+330612345678") is False

    def test_valide_plus33_fixe(self):
        assert validate("+33123456789") is True

    def test_invalide_chaine_vide(self):
        assert validate("") is False


class TestPhoneDetect:
    def test_detecte_national_dans_texte(self):
        spans = detect("Appelez le 0612345678 svp")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "0612345678"
        assert s.type.value == "TELEPHONE"
        assert s.start == 11
        assert s.end == 21
        assert s.confidence < 1.0

    def test_detecte_international_dans_texte(self):
        spans = detect("Tel: +33612345678.")
        assert len(spans) == 1
        assert spans[0].value == "+33612345678"

    def test_aucun_span_si_numero_non_fr(self):
        assert detect("Réf 1234567890 ici") == []

    def test_detecte_plusieurs_numeros(self):
        spans = detect("0612345678 et +33123456789")
        assert len(spans) == 2
