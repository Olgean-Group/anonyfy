"""Tests de mask_json / unmask_json (phase 18, préparation API v2).

Parcours récursif d'un arbre JSON: seules les feuilles ``str`` sont
masquées/démasquées. Les clés (dict keys), les valeurs structurelles
(int/float/bool/null/list/dict) et les chemins exemptés (ex. ``function.name``
pour la compatibilité tool-calling LLM, PRD §7) ne sont jamais touchés.

Référence: PLAN.md phase 18 (4 critères d'acceptation).
"""

from __future__ import annotations

import json

from anonyfy import Vault


def _vault(tmp_path) -> Vault:
    p = str(tmp_path / "reg.db")
    return Vault(key=b"0" * 16, scope="s", registry_path=p)


# --- Critère 2: exempt function.name + model, nom masqué -------------------


class TestExemptChemins:
    def test_plan_criterion2(self, tmp_path) -> None:
        v = _vault(tmp_path)
        payload = {
            "model": "gpt-4",
            "tools": [
                {
                    "function": {
                        "name": "chercher_client",
                        "parameters": {"nom": "M. Jean Dupont"},
                    }
                }
            ],
        }
        m = v.mask_json(
            payload,
            exempt=["$.tools[*].function.name", "$.model"],
        )
        assert m["model"] == "gpt-4"
        assert m["tools"][0]["function"]["name"] == "chercher_client"
        assert "Jean" not in json.dumps(m)

    def test_exempt_empeche_le_masquage_d_un_identifiant(self, tmp_path) -> None:
        """Si function.name contient un identifiant détectable (SIRET),
        l'exemption le préserve intact. Test non tautologique: sans exempt,
        vault.mask modifierait la valeur."""
        v = _vault(tmp_path)
        # Vérif préalable: vault.mask masque bien un SIRET seul.
        assert "73282932000033" not in v.mask("SIRET 73282932000033").text
        payload = {"tools": [{"function": {"name": "SIRET 73282932000033"}}]}
        m = v.mask_json(payload, exempt=["$.tools[*].function.name"])
        assert m["tools"][0]["function"]["name"] == "SIRET 73282932000033"

    def test_sans_exempt_function_name_est_masque(self, tmp_path) -> None:
        """Sans exemption, un identifiant dans function.name DOIT être masqué.
        Prouve que l'exemption agit réellement (le test précédent n'est pas
        tautologique)."""
        v = _vault(tmp_path)
        payload = {"tools": [{"function": {"name": "SIRET 73282932000033"}}]}
        m = v.mask_json(payload)  # exempt vide
        assert "73282932000033" not in m["tools"][0]["function"]["name"]


# --- Critère 3: round-trip JSON --------------------------------------------


class TestRoundTrip:
    def test_round_trip_siret(self, tmp_path) -> None:
        v = _vault(tmp_path)
        p = {"text": "SIRET 73282932000033"}
        m = v.mask_json(p)
        assert v.unmask_json(m) == p

    def test_round_trip_preserve_types_structurels(self, tmp_path) -> None:
        """Le round-trip préserve int/float/bool/null/list imbriqués."""
        v = _vault(tmp_path)
        p = {
            "n": 42,
            "f": 1.5,
            "b": True,
            "x": None,
            "lst": [1, "deux", False, None, {"k": "SIRET 73282932000033"}],
            "txt": "SIRET 73282932000033",
        }
        m = v.mask_json(p)
        assert v.unmask_json(m) == p

    def test_unmask_sur_deja_masque_restitue(self, tmp_path) -> None:
        v = _vault(tmp_path)
        p = {"text": "SIRET 73282932000033"}
        m = v.mask_json(p)
        # unmask_json sur le payload déjà masqué -> restitution exacte
        assert v.unmask_json(m) == p


# --- Qualité: clés, types, fuite -------------------------------------------


class TestInvariants:
    def test_cles_dict_inchangees(self, tmp_path) -> None:
        """Aucune clé (dict key) n'est modifiée par mask_json."""
        v = _vault(tmp_path)
        payload = {
            "model": "SIRET 73282932000033",
            "nested": {"SIRET 73282932000033": "SIRET 73282932000033"},
        }
        m = v.mask_json(payload)
        assert set(m.keys()) == {"model", "nested"}
        assert set(m["nested"].keys()) == {"SIRET 73282932000033"}
        # La clé reste le SIRET en clair (jamais masquée).
        assert "SIRET 73282932000033" in m["nested"].keys()

    def test_types_non_str_inchanges(self, tmp_path) -> None:
        """int/float/bool/null restent inchangés (pas des str)."""
        v = _vault(tmp_path)
        payload = {"n": 42, "f": 1.5, "b": True, "x": None}
        m = v.mask_json(payload)
        assert m == {"n": 42, "f": 1.5, "b": True, "x": None}
        assert v.unmask_json(m) == payload

    def test_pas_de_clair_dans_audit_via_json_walk(self, tmp_path) -> None:
        """Invariant 1: json_walk délègue à mask qui gère l'audit.
        On vérifie juste que mask_json ne fuit pas le clair dans le résultat."""
        v = _vault(tmp_path)
        payload = {"text": "SIRET 73282932000033"}
        m = v.mask_json(payload)
        assert "73282932000033" not in json.dumps(m)


# --- Cas limites -----------------------------------------------------------


class TestCasLimites:
    def test_liste_de_str_seulement_siret_masque(self, tmp_path) -> None:
        """Dans une liste de str, seule la str contenant un identifiant
        détecté est masquée; 'banane' (pas un identifiant) inchangée."""
        v = _vault(tmp_path)
        payload = {"items": ["SIRET 73282932000033", "banane"]}
        m = v.mask_json(payload)
        assert "73282932000033" not in m["items"][0]
        assert m["items"][1] == "banane"
        # Round-trip
        assert v.unmask_json(m) == payload

    def test_payload_vide_dict(self, tmp_path) -> None:
        v = _vault(tmp_path)
        assert v.mask_json({}) == {}
        assert v.unmask_json({}) == {}

    def test_payload_vide_list(self, tmp_path) -> None:
        v = _vault(tmp_path)
        assert v.mask_json([]) == []
        assert v.unmask_json([]) == []

    def test_payload_none(self, tmp_path) -> None:
        v = _vault(tmp_path)
        assert v.mask_json(None) is None
        assert v.unmask_json(None) is None

    def test_wildcard_index_matche_tous_les_elements(self, tmp_path) -> None:
        """$.tools[*].function.name matche tous les index du tableau."""
        v = _vault(tmp_path)
        payload = {
            "tools": [
                {"function": {"name": "SIRET 73282932000033"}},
                {"function": {"name": "SIRET 55212022200013"}},
            ]
        }
        m = v.mask_json(payload, exempt=["$.tools[*].function.name"])
        assert m["tools"][0]["function"]["name"] == "SIRET 73282932000033"
        assert m["tools"][1]["function"]["name"] == "SIRET 55212022200013"

    def test_exempt_modele_matche_cle_exacte(self, tmp_path) -> None:
        """$.model matche la clé exacte à la racine."""
        v = _vault(tmp_path)
        payload = {"model": "SIRET 73282932000033", "other": "SIRET 73282932000033"}
        m = v.mask_json(payload, exempt=["$.model"])
        # model exempté -> intact
        assert m["model"] == "SIRET 73282932000033"
        # other non exempté -> masqué
        assert "73282932000033" not in m["other"]
