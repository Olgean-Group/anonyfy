"""Critere d'acceptation D6: round-trip complet avec cle aleatoire regeneree.

Le test d'integration (D6/OBJ-004) verifie que le masquage est reversible avec
une cle aleatoire (non nulle) fraichement generee via ``os.urandom(16)``. Les
tests a cle nulle (``b'0'*16``) valident la logique metier mais pas la crypto
reelle; ce test garantit que le chiffrement FF3-1 fonctionne end-to-end avec une
cle aleatoire de 128 bits, sur un document couvrant plusieurs types (NIR,
SIRET, IBAN, telephone, date, patronyme, email).

``mask`` puis ``unmask`` sur le meme Vault (registre persistant) doit restituer
exactement le texte original. Une cle differente a chaque execution du test
verifie qu'il n'y a pas de valeur codee en dur dependante d'une cle specifique.

Reference: PRD section 10 D6, PLAN.md phase 19, decision D6.
"""

from __future__ import annotations

import os

from anonyfy import Vault

_SCOPE = "acceptance-random-key"

# Document couvrant plusieurs types structures et gazetteers. Les valeurs sont
# fictives (format valide, jamais de donnees reelles).
_TEXT = (
    "M. Jean Dupont, ne le 3 mai 1990, NIR 1234567890123 89, "
    "SIRET 73282932000033, IBAN FR76 1234 5678 9012 3456 7890 123, "
    "tel 06 12 34 56 78, email jean.dupont@exemple.fr"
)


def test_roundtrip_random_key(tmp_path):
    """mask puis unmask avec une cle aleatoire os.urandom(16) restitue l'original."""
    key = os.urandom(16)
    assert key != b"\x00" * 16, "la cle aleatoire ne doit pas etre nulle"
    v = Vault(key=key, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    try:
        masked = v.mask(_TEXT)
        # Le masque ne doit pas contenir aucune des valeurs claires sensibles
        # (garde-fou: on verifie que mask a transforme le texte).
        assert masked.text != _TEXT, "mask n'a rien modifie"
        restored = v.unmask(masked.text)
        assert restored == _TEXT, f"round-trip echoue avec cle aleatoire: {restored!r} != {_TEXT!r}"
    finally:
        v.close()


def test_roundtrip_two_distinct_random_keys(tmp_path):
    """Deux cles aleatoires differentes produisent des masques differents mais
    chacun se restitue exactement (la reversibilite ne depend pas d'une cle fixe)."""
    key_a = os.urandom(16)
    key_b = os.urandom(16)
    # On force key_b != key_a pour un test non flaky (probabilite de collision
    # 2^-128, mais on l'evite explicitement).
    while key_b == key_a:
        key_b = os.urandom(16)

    v_a = Vault(key=key_a, scope=_SCOPE, registry_path=str(tmp_path / "reg_a.db"))
    v_b = Vault(key=key_b, scope=_SCOPE, registry_path=str(tmp_path / "reg_b.db"))
    try:
        masked_a = v_a.mask(_TEXT)
        masked_b = v_b.mask(_TEXT)
        # Deux cles differentes -> des substituts tres probablement differents
        # (garde-fou de non-determinisme cross-key, invariant 2: determinisme scope).
        assert masked_a.text != masked_b.text, (
            "deux cles differentes produisent le meme masque (determinisme cross-key)"
        )
        assert v_a.unmask(masked_a.text) == _TEXT
        assert v_b.unmask(masked_b.text) == _TEXT
    finally:
        v_a.close()
        v_b.close()
