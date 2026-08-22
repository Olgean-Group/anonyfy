"""Tests de l'automate Aho-Corasick sur les substituts émis (phase 10b).

L'automate cherche **TOUJOURS les SURROGATES** dans le texte, jamais le clair
(invariant 1, architecture §6). Les variantes (``variants.py``) s'appliquent au
substitut, pas au clair.

Testé en isolation via ``from_surrogates([...])`` et en intégration registre→
automate via ``from_registry(r)`` (registre phase 10). N'invoque ni ``Vault.mask``
ni ``Vault.unmask`` (livrés en phase 08).

Référence: PLAN.md phase 10b, D7/OBJ-005, architecture §6, invariant 1.
"""

from __future__ import annotations

from anonyfy.resolve.aho_corasick import AhoCorasick, Hit

# --- Construction en isolation (from_surrogates) -----------------------------


class TestFromSurrogatesBasics:
    def test_from_surrogates_retrouve_substitut_literal(self):
        ac = AhoCorasick.from_surrogates(["41804261100034"])
        hits = ac.find("le siret 41804261100034 ici")
        assert any(h.substitute == "41804261100034" for h in hits)

    def test_from_surrogates_aucun_hit_si_absent(self):
        ac = AhoCorasick.from_surrogates(["41804261100034"])
        assert ac.find("aucun siret ici") == []

    def test_from_surrogates_retrouve_plusieurs_substituts_distincts(self):
        ac = AhoCorasick.from_surrogates(["41804261100034", "Pierre Dupont"])
        hits = ac.find("41804261100034 et Pierre Dupont")
        subs = {h.substitute for h in hits}
        assert "41804261100034" in subs
        assert "Pierre Dupont" in subs

    def test_from_surrogates_liste_vide_ne_match_rien(self):
        ac = AhoCorasick.from_surrogates([])
        assert ac.find("n'importe quoi") == []


# --- Variante SIRET reformaté par groupes de 3 (D7) --------------------------


class TestVarianteSiretGroupes:
    def test_retrouve_siret_reformate_par_groupes_de_3(self):
        sub = "41804261100034"
        ac = AhoCorasick.from_surrogates([sub])
        reformatted = " ".join(sub[i : i + 3] for i in range(0, len(sub), 3))
        hits = ac.find(reformatted)
        assert any(h.substitute == sub for h in hits)


# --- Variante « M. <nom> » d'un substitut patronyme (D7) ----------------------


class TestVarianteMonsieur:
    def test_retrouve_variante_monsieur_dupont(self):
        sub = "Pierre Dupont"
        ac = AhoCorasick.from_surrogates([sub])
        parts = sub.split()
        variant = f"M. {parts[-1]}" if len(parts) >= 2 else sub.upper()
        hits = ac.find(variant)
        assert any(h.substitute == sub for h in hits)


# --- Variante de casses ------------------------------------------------------


class TestVarianteCasses:
    def test_retrouve_minuscules(self):
        ac = AhoCorasick.from_surrogates(["Pierre Dupont"])
        hits = ac.find("pierre dupont")
        assert any(h.substitute == "Pierre Dupont" for h in hits)

    def test_retrouve_majuscules(self):
        ac = AhoCorasick.from_surrogates(["Pierre Dupont"])
        hits = ac.find("PIERRE DUPONT")
        assert any(h.substitute == "Pierre Dupont" for h in hits)


# --- Champs du Hit (contrat d'interface) -------------------------------------


class TestHitFields:
    def test_hit_expose_start_end_match_et_type(self):
        ac = AhoCorasick.from_surrogates(["41804261100034"])
        text = "xx41804261100034yy"
        hits = ac.find(text)
        assert len(hits) >= 1
        h = hits[0]
        assert isinstance(h, Hit)
        assert h.start == 2
        assert h.end == 16
        assert h.match == "41804261100034"
        assert h.substitute == "41804261100034"

    def test_hit_start_end_refleotent_la_position_du_match(self):
        ac = AhoCorasick.from_surrogates(["Pierre Dupont"])
        text = "avant Pierre Dupont apres"
        hits = ac.find(text)
        h = next(hit for hit in hits if hit.substitute == "Pierre Dupont")
        assert text[h.start : h.end] == "Pierre Dupont"


# --- Intégration registre→automate (from_registry, D7) ----------------------


class TestFromRegistry:
    def test_from_registry_retrouve_substitut_reserve(self, registry_with_entries):
        r, sub = registry_with_entries
        ac = AhoCorasick.from_registry(r)
        hits = ac.find(str(sub))
        assert any(h.substitute == str(sub) for h in hits)

    def test_from_registry_aucun_hit_pour_substitut_invente(self, registry):
        ac = AhoCorasick.from_registry(registry)
        assert ac.find("VALEUR_JAMAIS_EMISE_99999") == []

    def test_from_registry_retrouve_variante_digit_grouping(self, registry_with_entries):
        r, sub = registry_with_entries
        ac = AhoCorasick.from_registry(r)
        grouped = " ".join(str(sub)[i : i + 3] for i in range(0, len(str(sub)), 3))
        hits = ac.find(grouped)
        assert any(h.substitute == str(sub) for h in hits)


# --- Registre: lookup/contains (invariant 4 au niveau du registre) ----------


class TestRegistryLookupContains:
    def test_lookup_renvoie_enregistrement_pour_substitut_emis(self, registry_with_entries):
        r, sub = registry_with_entries
        rec = r.lookup(str(sub))
        assert rec is not None
        assert rec.surrogate == str(sub)

    def test_lookup_renvoie_none_pour_substitut_invente(self, registry):
        assert registry.lookup("VALEUR_JAMAIS_EMISE_99999") is None

    def test_contains_true_pour_substitut_emis(self, registry_with_entries):
        r, sub = registry_with_entries
        assert r.contains(str(sub)) is True

    def test_contains_false_pour_substitut_invente(self, registry):
        assert registry.contains("VALEUR_JAMAIS_EMISE_99999") is False

    def test_lookup_expose_index_hmac_mais_pas_le_clair(self, registry_with_entries):
        r, sub = registry_with_entries
        rec = r.lookup(str(sub))
        assert hasattr(rec, "clear_index")
        assert hasattr(rec, "clear_hmac")
        # invariant 1: le registre n'expose jamais la valeur claire
        assert not hasattr(rec, "clear_value")
        assert not hasattr(rec, "clear")

    def test_iter_surrogates_liste_les_substituts_emis(self, registry_with_entries):
        r, sub = registry_with_entries
        surrogates = r.iter_surrogates()
        assert str(sub) in surrogates


# --- Phase 27: frontières de mot (OBJ-REC-108 non-régression) ---------------


class TestWordBoundary:
    """Phase 27: l'Aho-Corasick ne doit pas matcher un substitut court à
    l'intérieur d'un mot plus long (ex. « ME » dans « MEGID »). Les hits sont
    filtrés par frontière de mot: un match ne commence ni ne finit au milieu
    d'un token de même classe (lettre/digit) que le substitut.

    Cause racine: le gazetteer INSEE complet (879k noms) contient des entrées
    courtes (1-3 lettres: « M », « ME », « ID ») qui, utilisées comme substituts,
    matchent par sous-chaîne dans l'Aho-Corasick à l'intérieur de mots non
    masqués, corrompant le round-trip unmask.
    """

    def test_substitut_court_ne_match_pas_dans_mot_plus_long(self):
        """« ME » substitut ne doit pas matcher dans « MEGID » (mot non masqué)."""
        ac = AhoCorasick.from_surrogates(["ME"])
        hits = ac.find("BLATTLIN GARCIA LAJEUS MEGID")
        # « ME » à la position 24 est suivi de « G » (lettre) → pas une frontière.
        me_hits = [h for h in hits if h.substitute == "ME"]
        assert me_hits == [], f"« ME » a matché dans « MEGID »: {me_hits}"

    def test_substitut_court_match_à_frontière_de_mot(self):
        """« ME » substitut matche quand il est un mot standalone (entre espaces)."""
        ac = AhoCorasick.from_surrogates(["ME"])
        hits = ac.find("BLATTLIN GARCIA LAJEUS ME FIN")
        me_hits = [h for h in hits if h.substitute == "ME"]
        assert len(me_hits) == 1
        assert me_hits[0].start == 23
        assert me_hits[0].end == 25

    def test_substitut_digit_ne_match_pas_dans_digit_plus_long(self):
        """« 42 » substitut ne doit pas matcher dans « 4242 »."""
        ac = AhoCorasick.from_surrogates(["42"])
        hits = ac.find("ID 4242 FIN")
        sub42 = [h for h in hits if h.substitute == "42"]
        assert sub42 == [], f"« 42 » a matché dans « 4242 »: {sub42}"

    def test_substitut_digit_match_à_frontière(self):
        """« 42 » substitut matche quand séparé par des espaces."""
        ac = AhoCorasick.from_surrogates(["42"])
        hits = ac.find("ID 42 FIN")
        sub42 = [h for h in hits if h.substitute == "42"]
        assert len(sub42) == 1

    def test_substitut_long_match_meme_sans_frontière_gauche_digit(self):
        """Un substitut digit précédé d'une lettre matche (classes différentes)."""
        ac = AhoCorasick.from_surrogates(["41804261100034"])
        hits = ac.find("xx41804261100034yy")
        assert any(h.substitute == "41804261100034" for h in hits)
