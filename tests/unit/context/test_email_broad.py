"""Détection email à alphabet local-part étendu (phase 13, D9).

Étend la détection phase 06 (alphabet ``[A-Za-z0-9._+-]``) à un alphabet large
pour la local-part: lettres accentuées, apostrophes ``'`` (U+0027) et ``’``
(U+2019), points, tirets, ``+``. La normalisation NFKC + minuscules et le
masquage FPE de la local-part relèvent du moteur (phase 13); ce module ne fait
que la détection (offsets, ``Span`` standard ``EntityType.EMAIL``).

Référence: PLAN.md phase 13 (D9, alphabet email pré-autorisé D21).
"""

from __future__ import annotations

from anonyfy.detect.context.email import detect
from anonyfy.types import EntityType


class TestDetectEmailBroad:
    def test_email_simple_ascii(self) -> None:
        spans = detect("Contact: jean.dupont@exemple.fr")
        emails = [s for s in spans if s.type == EntityType.EMAIL]
        assert len(emails) == 1
        assert emails[0].value == "jean.dupont@exemple.fr"

    def test_email_apostrophe_u0027(self) -> None:
        spans = detect("Contact: Jean.O'Brien@exemple.fr")
        emails = [s for s in spans if s.type == EntityType.EMAIL]
        assert len(emails) == 1
        # La local-part entière « Jean.O'Brien » est captée (pas seulement
        # « Brien » comme le validateur phase 06 qui exclut l'apostrophe).
        assert emails[0].value == "Jean.O'Brien@exemple.fr"

    def test_email_apostrophe_u2019(self) -> None:
        spans = detect("Écrit par O’hara@mail.com")
        emails = [s for s in spans if s.type == EntityType.EMAIL]
        assert len(emails) == 1
        assert emails[0].value == "O’hara@mail.com"

    def test_email_accents(self) -> None:
        spans = detect("Émail: rené.dupont@exemple.fr")
        emails = [s for s in spans if s.type == EntityType.EMAIL]
        assert len(emails) == 1
        assert emails[0].value == "rené.dupont@exemple.fr"

    def test_email_plus_et_tiret(self) -> None:
        spans = detect("perso: jean+tag-1@exemple.fr")
        emails = [s for s in spans if s.type == EntityType.EMAIL]
        assert len(emails) == 1
        assert emails[0].value == "jean+tag-1@exemple.fr"

    def test_offset_correct(self) -> None:
        text = "Contact: Jean.O'Brien@exemple.fr merci"
        spans = detect(text)
        for s in spans:
            if s.type == EntityType.EMAIL:
                assert text[s.start : s.end] == s.value

    def test_confiance_dans_plage(self) -> None:
        spans = detect("jean.o'brien@exemple.fr")
        for s in spans:
            assert 0.0 < s.confidence <= 1.0

    def test_texte_sans_email_renvoie_vide(self) -> None:
        assert detect("bonjour tout le monde") == []

    def test_domaine_avec_sous_domaines(self) -> None:
        spans = detect("mail: a.b@c.d.example.com")
        emails = [s for s in spans if s.type == EntityType.EMAIL]
        assert len(emails) == 1
        assert emails[0].value == "a.b@c.d.example.com"
