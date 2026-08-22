"""Test d'acceptance critère 4: 5000 patronymes distincts, zéro collision.

Sur un scope, 5000 patronymes distincts du gazetteer produisent 5000 substituts
distincts (injectivité scopée, invariant 3). La permutation Feistel bijective
sur l'index gazetteer garantit l'absence de collision.

Phase 34 (R1, D34b): un patronyme NU (sans déclencheur) n'est plus masqué en
policy permissive (candidat nu filtré). Les tests passent donc par un contexte
déclencheur ("M. ") pour conserver un masquage effectif et vérifier réellement
l'injectivité des substituts (non-trivialité).
"""

from anonyfy import Vault

_KEY = b"0" * 16

#: Noms mono-token (ni espace, ni apostrophe, ni tiret): les seuls qu'un
#: déclencheur "M. " encapsule en un seul span PATRONYME masqué. Les entrées
#: composées ("BEVEN BUNFORD") n'ont pas de token unique dans le gazetteer et
#: ne seraient pas masquées, ce qui viderait le test de substance.
def _patronymes_mono_token(count=5000):
    from anonyfy.detect.gazetteers.loader import load_noms

    return [
        e.name
        for e in load_noms()
        if " " not in e.name and "'" not in e.name and "-" not in e.name
    ][:count]


def test_5000_distinct_surnames(tmp_path):
    """5000 patronymes distincts -> 5000 substituts distincts."""
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    noms = _patronymes_mono_token(5000)
    assert len(noms) == 5000, "gazetteer n'a pas 5000 patronymes mono-token"
    substituts = set()
    for nom in noms:
        m = v.mask(f"M. {nom}")
        # Le substitut est la partie après "M. " (un autre patronyme du gazetteer)
        sub = m.text.removeprefix("M. ").strip()
        assert sub != nom, f"patronyme non masqué en contexte déclenché: {nom!r}"
        substituts.add(sub)
    assert len(substituts) == 5000, f"collision: {5000 - len(substituts)} substituts en doublon"
    v.close()


def test_5000_distinct_surnames_avec_contexte(tmp_path):
    """Variante: 5000 patronymes dans un contexte textuel, pas de collision."""
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    noms = _patronymes_mono_token(5000)
    substituts = set()
    for nom in noms:
        m = v.mask(f"M. {nom}")
        sub = m.text.removeprefix("M. ").strip()
        assert sub != nom, f"patronyme non masqué en contexte déclenché: {nom!r}"
        substituts.add(sub)
    assert len(substituts) == 5000
    v.close()


def test_collision_inter_type_prenom_patronyme(tmp_path):
    """Phase 27: avec le gazetteer INSEE complet (879k noms, 36k prénoms),
    la collision inter-type ADÈLE/CAULIER/TOUSSAINT du gazetteer 5k ne se
    reproduit plus (permutation différente sur 879k entrées). Le test
    confirme qu'aucune collision RegistryError n'est levée — la limite D26
    est levée par l'élargissement du gazetteer.

    Phase 34 (R1, D34b): les patronymes/prénoms nus ne sont plus masqués en
    permissive; on passe par un déclencheur "M. " pour obtenir un masquage
    effectif des deux types (PRENOM et PATRONYME) et exercer le registre.
    """
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    v.mask("M. ADÈLE")  # PRENOM -> substitut (gazetteer 36k prénoms)
    v.mask("M. CAULIER")  # PATRONYME -> substitut (gazetteer 879k noms)
    v.close()
