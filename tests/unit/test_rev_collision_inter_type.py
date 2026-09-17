"""Phase 63 — REGISTRY-COLLISION-INTER-TYPE (MAJEUR) + point fixe sondé non réversible.

Deux défauts liés à la réversibilité et à la disponibilité du masquage :

1. **Collision inter-type** : ``used_surrogates`` est global au registre, mais
   les permutations PRENOM et PATRONYME sont indépendantes. Un nom commun aux
   deux gazetteers peut produire le même substitut dans les deux types
   (ex. ``PRE('AARRON') == NOM('AUCHATRAIRE') == 'GALINA'``) : la seconde
   réservation lève ``RegistryError`` et **fait échouer ``mask``**. Mesure :
   8 249 collisions sur 23 227 prénoms purs (35 %).

2. **Point fixe sondé non réversible** : quand un substitut égale le clair
   (point fixe, ex. ``'Rue du Doubs'`` pour le type VOIE), ``_apply_fixed_point_probe``
   enregistre un substitut sondé **sans mémoriser le décalage** : au ``unmask``,
   la permutation inverse rend un autre nom. Le round-trip est faux.

Correctif : le sondage devient une propriété du registre (source unique des
substituts attribués), et l'offset est persisté dans ``clear_index`` — déjà
présent au schéma, colonne actuellement inutilisée pour les types gazetteer.
Au unmask, ``clear_index`` (offset) est retranché avant ``decrypt``.

Référence: BACKLOG REGISTRY-COLLISION-INTER-TYPE (D23, D26), invariant 2 et 4.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.surrogate.registry import ScopeRegistry

KEY = b"0" * 16

#: Collisions moteur vérifiées : PRE(X) == NOM(Y) pour la clé nulle, scope "s".
COLLISIONS_CONNUES = (
    ("AARRON", "AUCHATRAIRE"),
    ("ABD-EL", "ALZIEU"),
    ("ABDEL-KADER", "AZEVEDO LEMOS MARQUES"),
    ("ABDOUL-MALIK", "BANNOURA"),
    ("ABDOULHAKIM", "ASIKIN"),
)


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    yield v
    v.close()


class TestCollisionInterType:
    """Un prénom pur et un patronyme de substituts croisés ne bloquent plus."""

    @pytest.mark.parametrize("prenom,patronyme", COLLISIONS_CONNUES)
    def test_mask_ne_leve_pas_et_masque_les_deux(self, vault, prenom, patronyme):
        m1 = vault.mask(f"{prenom} Dupont")
        assert m1.entities, f"aucun span pour {prenom!r}"
        m2 = vault.mask(f"M. {patronyme}")
        assert m2.entities, f"aucun span pour {patronyme!r} (collision non résolue)"
        assert prenom.casefold() not in m1.text.casefold()
        assert patronyme.casefold() not in m2.text.casefold()

    @pytest.mark.parametrize("prenom,patronyme", COLLISIONS_CONNUES)
    def test_substituts_distincts_et_round_trip(self, vault, prenom, patronyme):
        """Les deux clairs gardent des substituts distincts (invariant 3) et
        le round-trip réussit (invariant 2)."""
        t1 = f"{prenom} Dupont"
        t2 = f"M. {patronyme}"
        w1 = vault.mask(t1)
        w2 = vault.mask(t2)
        subs1 = {s.value for s in w1.entities}
        subs2 = {s.value for s in w2.entities}
        assert not (subs1 & subs2), f"collision de substituts: {subs1 & subs2}"
        assert vault.unmask(w1.text) == t1
        assert vault.unmask(w2.text) == t2

    def test_collision_dans_un_meme_texte(self, vault):
        """Les deux clairs dans le MÊME document : masquage et round-trip."""
        prenom, patronyme = COLLISIONS_CONNUES[0]
        t = f"{prenom} Dupont et M. {patronyme} sont présents."
        w = vault.mask(t)
        assert prenom.casefold() not in w.text.casefold()
        assert patronyme.casefold() not in w.text.casefold()
        assert vault.unmask(w.text) == t


class TestPointFixeSondeReversible:
    """Un point fixe sondé reste réversible (offset mémorisé)."""

    @pytest.mark.parametrize("voie", ["Rue du Doubs", "HLM La Colombe"])
    def test_round_trip_voie_point_fixe(self, vault, voie):
        t = f"12 {voie}"
        w = vault.mask(t)
        assert voie.casefold() not in w.text.casefold(), f"point fixe non corrigé: {w.text!r}"
        assert vault.unmask(w.text) == t, (
            f"round-trip cassé sur point fixe {voie!r}: {w.text!r} -> "
            f"{vault.unmask(w.text)!r} != {t!r}"
        )

    def test_substitut_du_point_fixe_est_stable(self, vault):
        """Deux masquages successifs donnent le même substitut (invariant 2)."""
        t = "12 Rue du Doubs"
        first = vault.mask(t).text
        for _ in range(5):
            assert vault.mask(t).text == first


class TestSondageRegistre:
    """Le registre sonde (via une fonction de candidats) au lieu de lever."""

    def test_register_fpe_sonde_et_enregistre_la_collision(self, tmp_path):
        """Un substitut déjà attribué à un autre clair déclenche le sondage.

        ``probe(k)`` fournit les candidats successifs (le cipher gazetteer en
        production) ; le registre reste la source unique des substituts
        attribués et mémorise l'offset retenu.
        """
        reg = ScopeRegistry(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        try:
            first = reg.register_fpe("PRENOM", "andrena", surrogate="ROYCE")
            assert first == "ROYCE"
            second = reg.register_fpe(
                "PATRONYME", "adou", surrogate="ROYCE", probe=lambda k: f"SUB{k}"
            )
            assert second == "SUB1", f"le registre doit sonder, reçu {second!r}"
            assert reg.lookup(second) is not None
        finally:
            reg.close()

    def test_sondage_reste_deterministe(self, tmp_path):
        """Deux registres neufs, même séquence -> mêmes substituts (invariant 2)."""
        paths = [tmp_path / "a.db", tmp_path / "b.db"]
        results = []
        for path in paths:
            reg = ScopeRegistry(key=KEY, scope="s", registry_path=str(path))
            try:
                r1 = reg.register_fpe("PRENOM", "andrena", surrogate="ROYCE")
                r2 = reg.register_fpe(
                    "PATRONYME", "adou", surrogate="ROYCE", probe=lambda k: f"SUB{k}"
                )
                results.append((r1, r2))
            finally:
                reg.close()
        assert results[0] == results[1], f"non déterministe: {results}"

    def test_offset_est_memorise_dans_clear_index(self, tmp_path):
        """L'offset retenu est persisté (colonne ``clear_index``), pour le unmask."""
        reg = ScopeRegistry(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        try:
            reg.register_fpe("PRENOM", "andrena", surrogate="ROYCE")
            second = reg.register_fpe(
                "PATRONYME", "adou", surrogate="ROYCE", probe=lambda k: f"SUB{k}"
            )
            record = reg.lookup(second)
            assert record is not None
            assert record.clear_index == 1, (
                f"offset attendu 1, reçu {record.clear_index} (réversibilité cassée)"
            )
        finally:
            reg.close()

    def test_sans_probe_la_collision_leve_toujours(self, tmp_path):
        """Sans fonction de sondage (types FPE), la collision reste une erreur."""
        from anonyfy.surrogate.registry import RegistryError

        reg = ScopeRegistry(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        try:
            reg.register_fpe("SIRET", "73282932000033", surrogate="55061068501994")
            with pytest.raises(RegistryError):
                reg.register_fpe("SIREN", "732829320", surrogate="55061068501994")
        finally:
            reg.close()


class TestOffsetPersistant:
    """L'offset de sondage survit à la réouverture (réversibilité persistée)."""

    def test_round_trip_apres_reouverture(self, tmp_path):
        registry_path = tmp_path / "r.db"
        prenom, patronyme = COLLISIONS_CONNUES[0]
        t1 = f"{prenom} Dupont"
        t2 = f"M. {patronyme}"

        v1 = Vault(key=KEY, scope="s", registry_path=str(registry_path))
        try:
            w1 = v1.mask(t1)
            w2 = v1.mask(t2)
        finally:
            v1.close()

        v2 = Vault(key=KEY, scope="s", registry_path=str(registry_path))
        try:
            assert v2.unmask(w1.text) == t1, "round-trip prénom cassé après réouverture"
            assert v2.unmask(w2.text) == t2, "round-trip patronyme cassé après réouverture"
        finally:
            v2.close()

    def test_voie_point_fixe_apres_reouverture(self, tmp_path):
        registry_path = tmp_path / "r.db"
        t = "12 Rue du Doubs"
        v1 = Vault(key=KEY, scope="s", registry_path=str(registry_path))
        try:
            masked = v1.mask(t).text
        finally:
            v1.close()
        v2 = Vault(key=KEY, scope="s", registry_path=str(registry_path))
        try:
            assert v2.unmask(masked) == t, "offset de point fixe non persisté"
        finally:
            v2.close()


class TestNonRegressionTypesSansCollision:
    """Les types sans collision (FPE, CP, date, email) sont inchangés."""

    @pytest.mark.parametrize(
        "texte",
        [
            "SIRET 73282932000033",
            "NIR 275032917028004",
            "IBAN FR7630006000011234567890189",
            "TEL 0612345678",
            "mail@example.fr",
            "12 rue de la Paix",
            "16000 Angoulême",
        ],
    )
    def test_round_trip_inchange(self, vault, texte):
        w = vault.mask(texte)
        assert vault.unmask(w.text) == texte, f"round-trip cassé: {texte!r}"
        assert w.entities, f"aucun span pour {texte!r}"

    def test_types_gazetteer_sans_collision(self, vault):
        for texte in ("M. DUPONT", "Jean Dupont", "habite à Lyon", "Œuilly"):
            w = vault.mask(texte)
            assert vault.unmask(w.text) == texte, f"round-trip cassé: {texte!r}"

    def test_invariant4_tient(self, vault):
        """Un substitut jamais émis n'est pas déchiffré (invariant 4)."""
        vault.mask("M. DUPONT")
        result = vault.unmask("SIRET 41804261100008")
        assert result == "SIRET 41804261100008"
