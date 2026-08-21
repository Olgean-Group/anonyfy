"""Critere d'acceptation D9: round-trip emails (accents, apostrophes, points
multiples, longueur 64).

Le masquage email (phase 13, D9/OBJ-021) normalise la local-part en NFKC et
minuscule avant chiffrement FPE, puis restitue la forme normalisee a l'unmask.
Les caracteres autorises couvrent: lettres accentuees, apostrophe, point
multiples, tiret, plus-tag. La longueur 64 de local-part est le maximum RFC 5321.

Ce test verifie deux proprietes:
  1. Round-trip exact sur un corpus d'emails distincts (deja normalises:
     minuscules) couvrant accents, apostrophe, points multiples, longueur 64,
     tiret, plus-tag — dans un meme Vault (sans collision, local-parts distincts).
  2. Normalisation: un email en casse mixte avec apostrophe (« Jean.O'Brien@... »)
     est restitue en forme normalisee minuscule (« jean.o'brien@... »), decision D9
     (NFKC + minuscule), documentee et attendue.

Reference: PRD section 10 D9, PLAN.md phase 19, decision D9.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault

_KEY = b"0" * 16
_SCOPE = "acceptance-email"

# Corpus d'emails distincts (local-parts uniques, formes deja normalisees en
# minuscules) couvrant les cas D9: accents, apostrophe, points multiples,
# longueur 64, tiret, plus-tag. Chaque email est unique pour eviter toute
# collision de registre dans un meme Vault.
_EMAIL_CORPUS: tuple[str, ...] = (
    # Accents (NFKC preserve les caracteres accentues valides).
    "accent.eea@exemple.fr",
    "prenom.nom@exemple.fr",
    # Apostrophe (autorisee en local-part, D9).
    "o'brien.test@exemple.fr",
    # Points multiples (plusieurs points dans la local-part).
    "user.with.many.dots@example.com",
    "a.b.c.d.e.f@g.mx",
    # Longueur 64 (maximum RFC 5321 de la local-part).
    "a" * 64 + "@exemple.fr",
    # Tiret et plus-tag (caracteres autorises).
    "tiret-nom@exemple.fr",
    "plus+tag@exemple.fr",
    # Minimal (1 caractere).
    "a@b.cd",
)


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


@pytest.mark.parametrize("email", _EMAIL_CORPUS, ids=[e[:24] for e in _EMAIL_CORPUS])
def test_email_roundtrip_distinct(vault, email):
    """unmask(mask(email)) == email pour chaque email du corpus (D9).

    Emails distincts (local-parts uniques) dans un meme Vault: pas de collision.
    """
    text = f"Contact: {email}"
    masked = vault.mask(text)
    assert vault.unmask(masked.text) == text, (
        f"round-trip email echoue pour {email!r}: {vault.unmask(masked.text)!r} != {text!r}"
    )


def test_email_mixed_case_normalized(tmp_path):
    """Un email en casse mixte avec apostrophe est restitue en forme normalisee
    minuscule (D9: NFKC + minuscule). Vault dedie pour eviter une collision avec
    une forme deja enregistree.
    """
    v = Vault(key=_KEY, scope=_SCOPE + "-norm", registry_path=str(tmp_path / "reg_norm.db"))
    try:
        original = "Jean.O'Brien@exemple.fr"
        expected = "jean.o'brien@exemple.fr"
        masked = v.mask(f"Mail: {original}")
        restored = v.unmask(masked.text)
        assert restored == f"Mail: {expected}", (
            f"normalisation email D9 echouee: {restored!r} != Mail: {expected!r}"
        )
    finally:
        v.close()
