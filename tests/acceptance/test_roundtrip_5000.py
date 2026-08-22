"""Test de non-régression phase 26 (B2): round-trip 5 000 patronymes.

Round-trip ``unmask(mask(x)) == x`` sur 5 000 patronymes distincts du gazetteer
dans un scope unique (scénario contentieux de masse). Le registre accumule
jusqu'à 5 000 substituts; l'automate Aho-Corasick reconstruit à chaque ``unmask``
doit arbitrer les hits chevauchants par longueur décroissante (le hit le plus
long gagne les overlaps) avant la substitution droite-à-gauche (OBJ-REC-106).

Référence: PLAN.md phase 26, critère d'acceptation « Non-régression 5 000 ».
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import load_noms
from anonyfy.surrogate.case_pattern import apply_case
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "roundtrip-5000"
_COUNT = 5000


@pytest.fixture(scope="module")
def noms() -> list[str]:
    """5 000 patronymes distincts du gazetteer (forme majuscule SIRENE)."""
    all_noms = [e.name for e in list(load_noms())[:_COUNT]]
    assert len(all_noms) == _COUNT, "gazetteer n'a pas assez de patronymes"
    return all_noms


@pytest.fixture(scope="module")
def vault(tmp_path_factory) -> Vault:
    """Vault avec un scope unique et registre persistant pour tout le module."""
    d = tmp_path_factory.mktemp("roundtrip5000")
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(d / "reg.db"))
    yield v
    v.close()


class TestRoundTrip5000:
    """unmask(mask(x)) == x sur 5 000 patronymes dans un scope unique."""

    def test_5000_patronymes_roundtrip(self, vault, noms):
        """Round-trip exact pour chacun des 5 000 patronymes.

        Le registre accumule tous les substituts; l'Aho-Corasick doit arbitrer
        les hits chevauchants (un substitut préfixe d'un autre) par longueur
        décroissante avant la substitution droite-à-gauche.

        Les 5 000 textes masqués sont concaténés (un par ligne) et démasqués en
        un seul appel ``unmask`` (une construction Aho-Corasick avec les 5 000
        substituts du registre). Le résultat est comparé ligne par ligne au
        clair attendu. Cela équivaut à 5 000 round-trips individuels tout en
        restant praticable (une construction d'automate au lieu de 5 000).
        """
        # Masker les 5 000 noms (le registre accumule les substituts).
        masked_lines = [vault.mask(nom).text for nom in noms]
        # Concaténer (séparateur "\n" non touché par unmask) et démasquer en
        # un seul appel.
        big_masked = "\n".join(masked_lines)
        big_clear = vault.unmask(big_masked)
        clear_lines = big_clear.split("\n")
        assert len(clear_lines) == len(noms), f"nb lignes: {len(clear_lines)} != {len(noms)}"
        failures: list[str] = []
        for i, (nom, line) in enumerate(zip(noms, clear_lines, strict=True)):
            if line != nom:
                failures.append(f"ligne {i}: {nom!r} -> masked {masked_lines[i]!r} -> {line!r}")
                if len(failures) >= 10:
                    break
        assert not failures, f"{len(failures)} round-trip(s) échoué(s) sur 5 000:\n" + "\n".join(
            failures
        )

    def test_substituts_adjacents_colles(self, vault, noms):
        """Substituts adjacents sans séparateur (cas LLM sans espacement).

        Deux patronymes masqués dans le même scope; on colle leurs substituts
        sans séparateur et on vérifie que ``unmask`` retrouve les deux clairs
        collés. L'arbitrage par longueur décroissante (OBJ-REC-106) garantit que
        le hit le plus long gagne les overlaps.
        """
        a, b = noms[0], noms[1]
        ma = vault.mask(a)
        mb = vault.mask(b)
        sub_a = ma.text
        sub_b = mb.text
        # Coller les substituts sans séparateur (réponse LLM sans espacement).
        colles = sub_a + sub_b
        rt = vault.unmask(colles)
        assert rt == a + b, f"substituts collés {colles!r} -> unmasked {rt!r}, attendu {a + b!r}"

    def test_arbitrage_match_exact_vs_variante(self, vault, noms):
        """B2b: un match exact gagne sur une variante de casse de même longueur.

        Inscrit au registre deux substituts de casses différentes (ex. un
        patronyme ``BONY`` majuscule et une commune ``Bony`` Title Case)
        produisant le même pattern Aho-Corasick via les variantes de casse
        (``BONY`` upper de ``Bony``). L'Aho-Corasick émet deux hits pour le span
        ``BONY``: un match exact (``BONY``) et une variante (``Bony``). Le
        tiebreak ``is_exact`` (match == substitut) départage: le match exact
        gagne. Retirer ``is_exact`` du tri fait échouer ce test (la variante
        ``Bony`` gagne par ordre stable et restitue le mauvais clair).

        On parcourt toutes les collisions de variante du registre et on vérifie
        que le unmask de chaque substitut exact restitue son clair (pas le clair
        de la variante). Sans ``is_exact``, les collisions où la variante est
        insérée avant le match exact dans l'Aho-Corasick (ex. ``Bony`` COMMUNE
        enregistrée avant ``BONY`` PATRONYME) produisent un hit variante qui
        gagne l'arbitrage par ordre stable.
        """
        # S'assurer que le registre contient les 5 000 substituts (le fixture
        # module partage le Vault avec test_5000_patronymes_roundtrip qui masque
        # les 5 000 noms en premier; on masque aussi par sécurité).
        surrogate_set = set(vault._registry.iter_surrogates())
        if len(surrogate_set) < 1000:
            for nom in noms:
                vault.mask(nom)
            surrogate_set = set(vault._registry.iter_surrogates())

        # Trouver toutes les collisions: un substitut majuscule ``sub`` dont la
        # forme Title Case ``sub.title()`` est aussi un substitut d'un type
        # différent (ex. ``BONY`` PATRONYME vs ``Bony`` COMMUNE).
        collisions: list[tuple[str, str]] = []
        for sub in sorted(surrogate_set):
            title_form = sub.title()
            if title_form == sub or title_form not in surrogate_set:
                continue
            rec_sub = vault._registry.lookup(sub)
            rec_title = vault._registry.lookup(title_form)
            if rec_sub is None or rec_title is None:
                continue
            if rec_sub.entity_type == rec_title.entity_type:
                continue
            collisions.append((sub, title_form))
        assert collisions, "aucune collision de variante trouvée dans le registre"

        # Pour chaque collision, le unmask du substitut exact doit restituer
        # le clair de sub (pas le clair de title_form, la variante).
        failures: list[str] = []
        for sub, title_form in collisions:
            rec_sub = vault._registry.lookup(sub)
            etype = EntityType.coerce(rec_sub.entity_type)
            expected = vault._engine.decrypt_surrogate(etype, sub)
            if rec_sub.case_pattern is not None:
                expected = apply_case(expected, rec_sub.case_pattern)
            rt = vault.unmask(sub)
            if rt != expected:
                failures.append(
                    f"{sub!r} ({rec_sub.entity_type}) -> unmask {rt!r}, "
                    f"attendu {expected!r} (variante {title_form!r} a gagné)"
                )
        assert not failures, (
            f"{len(failures)} collision(s) de variante échouée(s) sur "
            f"{len(collisions)}:\n" + "\n".join(failures)
        )
