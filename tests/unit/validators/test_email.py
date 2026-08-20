"""Tests du validateur email (phase 06).

Logique testée: syntaxe RFC simple (local-part@domaine.tld). Pas de clé de
contrôle arithmétique: la confiance est inférieure à 1.0. Mitigation des faux
positifs via ancrage et exclusion d'espaces/caractères invalides.
"""

from __future__ import annotations

from anonyfy.detect.validators.email import detect, validate


class TestEmailValidate:
    def test_valide_simple(self):
        assert validate("jean.dupont@exemple.fr") is True

    def test_valide_minuscule_domaine(self):
        assert validate("contact@start-up.com") is True

    def test_invalide_sans_arobase(self):
        assert validate("jean.dupontexemple.fr") is False

    def test_invalide_sans_domaine(self):
        assert validate("jean@") is False

    def test_invalide_sans_local_part(self):
        assert validate("@exemple.fr") is False

    def test_invalide_espaces(self):
        assert validate("jean dupont@exemple.fr") is False

    def test_invalide_arobase_double(self):
        assert validate("a@b@c.fr") is False

    def test_invalide_sans_tld(self):
        assert validate("jean@localhost") is False

    def test_invalide_chaine_vide(self):
        assert validate("") is False

    def test_valide_sous_domaine(self):
        assert validate("user@mail.exemple.fr") is True


class TestEmailDetect:
    def test_detecte_email_dans_texte(self):
        spans = detect("Contact: jean.dupont@exemple.fr merci")
        assert len(spans) == 1
        s = spans[0]
        assert s.value == "jean.dupont@exemple.fr"
        assert s.type.value == "EMAIL"
        assert s.start == 9
        assert s.end == 31
        assert s.confidence < 1.0

    def test_aucun_span_si_invalide(self):
        assert detect("pas un email: jean@") == []

    def test_detecte_plusieurs_emails(self):
        spans = detect("a@x.fr et b@y.com")
        assert len(spans) == 2

    def test_pas_de_match_dans_url(self):
        # Une URL ne doit pas produire un span email sur sa partie.
        assert detect("https://exemple.fr/path") == []
