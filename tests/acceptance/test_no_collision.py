"""Test d'acceptance critère 4: 5000 patronymes distincts, zéro collision.

Sur un scope, 5000 patronymes distincts du gazetteer produisent 5000 substituts
distincts (injectivité scopée, invariant 3). La permutation Feistel bijective
sur l'index gazetteer garantit l'absence de collision.
"""

import pytest

from anonyfy import Vault

_KEY = b"0" * 16


def test_5000_distinct_surnames(tmp_path):
    """5000 patronymes distincts -> 5000 substituts distincts."""
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    # 5000 patronymes du gazetteer (forme majuscule SIRENE)
    from anonyfy.detect.gazetteers.loader import load_noms
    noms = [e.name for e in list(load_noms())[:5000]]
    assert len(noms) == 5000, "gazetteer n'a pas 5000 patronymes"
    substituts = set()
    for nom in noms:
        m = v.mask(nom)
        # Le substitut est m.text (un autre patronyme du gazetteer)
        sub = m.text.strip()
        substituts.add(sub)
    assert len(substituts) == 5000, (
        f"collision: {5000 - len(substituts)} substituts en doublon"
    )
    v.close()


def test_5000_distinct_surnames_avec_contexte(tmp_path):
    """Variante: 5000 patronymes dans un contexte textuel, pas de collision."""
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    from anonyfy.detect.gazetteers.loader import load_noms
    noms = [e.name for e in list(load_noms())[:5000]]
    substituts = set()
    for nom in noms:
        t = f"Mr {nom}"
        m = v.mask(t)
        # m.text == "Mr <substitut>" (Mr n'est pas masqué)
        sub = m.text.replace("Mr ", "").strip()
        substituts.add(sub)
    assert len(substituts) == 5000
    v.close()