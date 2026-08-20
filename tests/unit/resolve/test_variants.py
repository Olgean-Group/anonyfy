"""Tests du dictionnaire de variantes des substituts (phase 10b).

Les variantes s'appliquent au **substitut** (surrogate), pas au clair
(invariant 1, architecture §6). Testé en isolation sur des substituts de test
connus: un SIRET FPE-valide et un patronyme de gazetteer.

Classes de variantes bornées couvertes (PLAN phase 10b): espaces, ponctuation,
casses, groupes de chiffres, « M. <nom> ». Les variantes exotiques ne sont pas
couvertes (documenté comme limite dans le PLAN).

Référence: PLAN.md phase 10b, D7/OBJ-005, architecture §6.
"""

from __future__ import annotations

from anonyfy.resolve import variants

# --- Groupes de chiffres (SIRET reformaté par groupes de 3) ------------------


class TestGroupesChiffres:
    def test_groupes_chiffres_reformate_par_3(self):
        sub = "41804261100034"
        assert "418 042 611 000 34" in variants.expand(sub)

    def test_groupes_chiffres_conserve_le_substitut_original(self):
        sub = "41804261100034"
        assert sub in variants.expand(sub)

    def test_groupes_chiffres_inchange_si_trop_court(self):
        # 2 chiffres: pas de variante de regroupement (garderait la même chaîne)
        assert variants.expand("42") == ["42"]

    def test_groupes_chiffres_ne_se_applique_pas_aux_patronymes(self):
        expanded = variants.expand("Pierre Dupont")
        # aucun substitut non numérique ne reçoit de variante « par groupes de 3 »
        assert not any(v.count(" ") >= 2 and all(p.isdigit() for p in v.split()) for v in expanded)


# --- Casses (minuscules / majuscules) ----------------------------------------


class TestCasses:
    def test_casses_minuscules(self):
        assert "pierre dupont" in variants.expand("Pierre Dupont")

    def test_casses_majuscules(self):
        assert "PIERRE DUPONT" in variants.expand("Pierre Dupont")

    def test_casses_inchange_pour_chiffres(self):
        expanded = variants.expand("41804261100034")
        assert "41804261100034" in expanded


# --- Espaces (collapsage / suppression) --------------------------------------


class TestEspaces:
    def test_espaces_supprime_les_espaces(self):
        assert "PierreDupont" in variants.expand("Pierre Dupont")

    def test_espaces_normalise_espaces_multiples(self):
        assert "Pierre Dupont" in variants.expand("Pierre  Dupont")

    def test_espaces_conserve_original(self):
        assert "Pierre Dupont" in variants.expand("Pierre Dupont")


# --- Ponctuation (formes avec / sans point du préfixe « M. ») ----------------


class TestPonctuation:
    def test_ponctuation_monsieur_avec_point(self):
        assert "M. Dupont" in variants.expand("Pierre Dupont")

    def test_ponctuation_monsieur_sans_point(self):
        assert "M Dupont" in variants.expand("Pierre Dupont")

    def test_ponctuation_monsieur_point_colle(self):
        assert "M.Dupont" in variants.expand("Pierre Dupont")


# --- « M. <nom> » (prénom substitué séparément) ------------------------------


class TestMonsieurDupont:
    def test_monsieur_dupont_genere_forme_monsieur(self):
        assert "M. Dupont" in variants.expand("Pierre Dupont")

    def test_monsieur_dupont_utilise_dernier_token(self):
        # « Pierre Paul Dupont » -> « M. Dupont » (dernier token = nom)
        assert "M. Dupont" in variants.expand("Pierre Paul Dupont")

    def test_monsieur_dupont_inchange_si_un_seul_token(self):
        assert "M. Durand" not in variants.expand("Durand")
        assert "Durand" in variants.expand("Durand")


# --- Invariants du dictionnaire de variantes --------------------------------


class TestInvariant:
    def test_expand_renvoie_vide_pour_substitut_vide(self):
        assert variants.expand("") == []

    def test_expand_ne_renvoie_jamais_vide_pour_substitut_non_vide(self):
        assert variants.expand("41804261100034")

    def test_expand_le_substitut_est_toujours_present(self):
        for sub in ["41804261100034", "Pierre Dupont", "004287"]:
            assert sub in variants.expand(sub)

    def test_expand_ne_renvoie_pas_de_doublons(self):
        expanded = variants.expand("Pierre Dupont")
        assert len(expanded) == len(set(expanded))

    def test_expand_ne_renvoie_jamais_de_chaine_vide(self):
        for sub in ["Pierre Dupont", "41804261100034", "004287"]:
            assert all(v for v in variants.expand(sub))
