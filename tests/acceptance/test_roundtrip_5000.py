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

    def test_arbitrage_match_exact_vs_variante(self, tmp_path_factory):
        """B2b: un match exact gagne sur une variante de casse de même longueur.

        Phase 27 OBJ-REC-108: test déterministe par collision synthétique. On
        inscrit directement deux substituts de casses différentes (``BONY``
        PATRONYME majuscule et ``Bony`` COMMUNE Title Case) via ``register_fpe``.
        L'Aho-Corasick émet deux hits pour le span ``BONY``: un match exact
        (``BONY``) et une variante (``Bony`` dont la variante upper = ``BONY``).
        Le tiebreak ``is_exact`` (match == substitut) départage: le match exact
        gagne. Retirer ``is_exact`` du tri fait échouer ce test (la variante
        ``Bony`` gagne par ordre stable et restitue le mauvais clair).
        """

        from anonyfy.surrogate.case_pattern import apply_case as _apply_case

        d = tmp_path_factory.mktemp("arbiter-exact")
        v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(d / "arb.db"))
        try:
            # Forcer l'initialisation paresseuse des ciphers patronyme/commune
            # pour pouvoir décrypter les substituts synthétiques.
            clear_patronyme = v._engine.decrypt_surrogate(EntityType.PATRONYME, "BONY")
            clear_commune = v._engine.decrypt_surrogate(EntityType.COMMUNE, "Bony")
            assert clear_patronyme is not None, "BONY pas dans le gazetteer noms"
            assert clear_commune is not None, "Bony pas dans le gazetteer communes"
            assert clear_patronyme != clear_commune, (
                "BONY et Bony doivent décrypter vers des clairs distincts"
            )

            # Inscrire la collision SYNTHÉTIQUE: BONY (PATRONYME, U:U) et
            # Bony (COMMUNE, T:T). Le registre ne peut pas refuser: les substituts
            # sont des chaînes distinctes (cas différent).
            v._registry.register_fpe(
                "patronyme", clear_patronyme, surrogate="BONY", case_pattern="U:U"
            )
            v._registry.register_fpe("commune", clear_commune, surrogate="Bony", case_pattern="T:T")

            # Le unmask de « BONY » doit restituer le clair PATRONYME (match
            # exact), pas le clair COMMUNE (variante de casse). Sans is_exact,
            # la variante « Bony » (inscrite en second) gagne par ordre stable
            # et restitue le clair COMMUNE.
            expected = _apply_case(clear_patronyme, "U:U")
            rt = v.unmask("BONY")
            assert rt == expected, (
                f"unmask('BONY') = {rt!r}, attendu {expected!r} (clair PATRONYME). "
                f"La variante Bony/COMMUNE a vraisemblablement gagné l'arbitrage."
            )
        finally:
            v.close()
