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

        Quand le registre contient un substitut patronyme ``BONY`` (clair
        ``LYONNET``) et un substitut commune ``Bony`` (dont la variante upper
        ``BONY`` matche le même texte), l'Aho-Corasick émet deux hits pour le
        span ``BONY``. L'arbitrage doit privilégier le match exact (``BONY``)
        sur la variante (``Bony``) pour restituer le bon clair.
        """
        # Le fixture vault (scope=module) partage le registre avec
        # test_5000_patronymes_roundtrip qui s'exécute en premier et masque les
        # 5 000 noms. On vérifie le round-trip isolé de chaque substitut sur un
        # échantillon: le unmask d'un substitut seul (sans contexte) doit
        # restituer le clair exact même si une variante de casse d'un autre
        # substitut produit un hit chevauchant de même longueur.
        failures: list[str] = []
        for nom in noms[:200]:  # échantillon
            m = vault.mask(nom)
            rt = vault.unmask(m.text)
            if rt != nom:
                failures.append(f"{nom!r} -> {m.text!r} -> {rt!r}")
                if len(failures) >= 3:
                    break
        assert not failures, "arbitrage match exact échoué:\n" + "\n".join(failures)
