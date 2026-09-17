"""Phase 55 — OE-LIGATURE-DETECT (REV backlog) : ligatures œ/Œ/æ/Æ fuient.

Le détecteur tokenisait avec ``[A-Za-zÀ-ÿ'’-]`` : la ligature « œ » (U+0153) et
« Œ » (U+0152) sont AU-DESSUS de U+00FF, donc hors classe. Un token contenant
une ligature était tronqué au « œ » et ne matchait plus le gazetteer : la
commune n'était pas masquée du tout (fuite, invariant 1) ou seulement
partiellement (fragments du clair subsistaient dans le texte masqué).

Mesure sur le gazetteer embarqué : 105 communes contiennent « œ » ; 73 n'étaient
JAMAIS masquées et 9 étaient masquées partiellement (fragments en clair).

Référence: BACKLOG OE-LIGATURE-DETECT.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import load_communes
from anonyfy.types import EntityType

KEY = b"0" * 16


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    yield v
    v.close()


def _communes_ligature() -> list[str]:
    return sorted(e.name for e in load_communes() if "œ" in e.name.casefold())


def _fragments_fuite(nom: str, masque: str) -> list[str]:
    """Fragments longs du clair encore présents dans le texte masqué."""
    return [
        partie
        for partie in nom.replace("’", "'").split("-")
        if len(partie) > 4 and partie.casefold() in masque.casefold()
    ]


class TestCommunesLigature:
    """Aucune commune à ligature ne doit laisser de fragment en clair."""

    @pytest.mark.parametrize(
        "nom",
        [
            "Cœuvres-et-Valsery",
            "Mons-en-Barœul",
            "Vandœuvre-lès-Nancy",
            "Bœurs-en-Othe",
            "Vœuil-et-Giget",
            "Plœuc-L'Hermitage",
            "Crèvecœur-sur-l'Escaut",
            "Œuilly",
        ],
    )
    def test_commune_en_contexte_adresse_masquee_entierement(self, vault, nom):
        t = f"Il habite à {nom}."
        m = vault.mask(t)
        fragments = _fragments_fuite(nom, m.text)
        assert not fragments, f"fragments du clair {nom!r} en clair dans {m.text!r}: {fragments}"
        assert nom.casefold() not in m.text.casefold(), (
            f"la commune {nom!r} n'est pas masquée: {m.text!r}"
        )
        assert m.entities, f"aucun span émis pour {nom!r}"

    def test_toutes_les_communes_ligature_sans_fragment(self, vault):
        """Balayage complet du gazetteer : 0 fragment en clair sur les 105."""
        communes = _communes_ligature()
        assert len(communes) >= 100, f"gazetteer inattendu: {len(communes)} communes"
        en_fuite: list[tuple[str, str]] = []
        for nom in communes:
            t = f"Il habite à {nom}."
            m = vault.mask(t)
            if _fragments_fuite(nom, m.text):
                en_fuite.append((nom, m.text))
        assert not en_fuite, f"communes à ligature encore en clair: {en_fuite[:5]}"

    def test_round_trip_commune_ligature(self, vault):
        t = "Il habite à Mons-en-Barœul."
        m = vault.mask(t)
        assert vault.unmask(m.text) == t, "round-trip échoué sur une commune à ligature"


class TestLigatureMajusculeEnInitiale:
    """La ligature capitale « Œ » est tokenisée (cause racine corrigée).

    En position d'initiale de prose SANS indice d'adresse, le toponyme est
    préservé (règle D42b/D42c, comme « Le maire de Paris. »). Le test vérifie
    donc (a) que le span COMMUNE existe dans le gazetteer (tokenisation
    correcte) et (b) qu'en contexte d'adresse il est bien masqué.
    """

    def test_oeuilly_tokenise_dans_le_gazetteer(self, vault):
        t = "Œuilly est une commune de l'Aisne."
        observe = vault.mask(t, observe=True)
        communes = [s for s in observe.entities if s.type == EntityType.COMMUNE]
        assert communes, (
            "« Œuilly » (Œ initial) n'est pas tokenisé comme commune : "
            f"ligature non couverte par la classe de tokens ({observe.entities!r})"
        )
        assert t[communes[0].start : communes[0].end] == "Œuilly"

    def test_oeuilly_masque_en_contexte_adresse(self, vault):
        t = "Il habite à Œuilly."
        m = vault.mask(t)
        assert "Œuilly" not in m.text, f"« Œuilly » (Œ initial) fuit: {m.text!r}"
        assert m.entities, "aucun span émis pour « Œuilly » en contexte d'adresse"


class TestVoiesLigature:
    """Les voies du gazetteer contenant une ligature restent masquables."""

    @pytest.mark.parametrize(
        "nom",
        ["Rue Pierre de Mercœur", "Allée Sœur Nelly", "Route d'Œillet"],
    )
    def test_voie_ligature_masquee(self, vault, nom):
        t = f"Le siège est au 12 {nom}."
        m = vault.mask(t)
        fragments = _fragments_fuite(nom, m.text)
        assert not fragments, f"fragments de voie en clair: {fragments} dans {m.text!r}"


class TestNonRegressionSansLigature:
    """Aucune régression sur les tokens sans ligature (contrôle)."""

    @pytest.mark.parametrize(
        "nom",
        ["Angoulême", "Saint-Étienne", "Marseille"],
    )
    def test_tokens_sans_ligature_toujours_masques(self, vault, nom):
        t = f"Il habite à {nom}."
        m = vault.mask(t)
        assert nom.casefold() not in m.text.casefold(), f"{nom!r} fuit: {m.text!r}"


class TestTokenisationDirecte:
    """La classe de token couvre les ligatures (contrôle unitaire de la cause)."""

    def test_places_token_re_couvre_les_ligatures(self):
        from anonyfy.detect.context.places import _TOKEN_RE

        for texte, attendu in (
            ("Mons-en-Barœul", "Mons-en-Barœul"),
            ("CœURS", "CœURS"),
            ("Œuilly", "Œuilly"),
            ("Lætitia", "Lætitia"),
        ):
            matched = [m.group(0) for m in _TOKEN_RE.finditer(texte)]
            assert attendu in matched, f"_TOKEN_RE(places) ne couvre pas {attendu!r}: {matched}"

    def test_triggers_token_re_couvre_la_ligature_majuscule(self):
        from anonyfy.detect.context.triggers import _TOKEN_RE

        matched = [m.group(0) for m in _TOKEN_RE.finditer("Œuilly")]
        assert matched == ["Œuilly"], f"triggers._TOKEN_RE a tronqué: {matched}"


class TestYTremaMajuscule:
    """Phase 63 : « Ÿ » (U+0178) est hors de `À-ÿ` (U+00C0-U+00FF), comme « œ ».

    Même famille que OE-LIGATURE-DETECT : le token était tronqué au « Ÿ » et le
    round-trip devenait faux (fragment du substitut laissé en place).
    """

    @pytest.mark.parametrize("texte", ["ALOŸS Dupont", "AŸDEN Dupont", "Jean ALOŸS"])
    def test_round_trip_y_trema(self, vault, texte):
        w = vault.mask(texte)
        assert vault.unmask(w.text) == texte, (
            f"round-trip cassé sur « Ÿ »: {texte!r} -> {w.text!r} -> {vault.unmask(w.text)!r}"
        )

    def test_tokenisation_couvre_y_trema(self):
        from anonyfy.detect.context.places import _TOKEN_RE

        matched = [m.group(0) for m in _TOKEN_RE.finditer("ALOŸS")]
        assert matched == ["ALOŸS"], f"« Ÿ » tronqué: {matched}"
