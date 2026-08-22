"""Phase 28 — S3: typage patronyme (interdiction du repli communes).

Un token capté comme patronyme par déclencheur contextuel (« M. », « Mme »…) ne
doit jamais être substitué par une commune, même si ce token est aussi présent
dans le gazetteer des communes (ex. BOISSEAU, CHAMPAGNE). L'arbitrage fait gagner
le typage PATRONYME sur COMMUNE en présence d'un déclencheur.

Référence: PLAN.md phase 28, PRD F3 (substitut de même type), critères 1-6.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.resolve.arbitrage import resolve_overlaps
from anonyfy.types import EntityType, Span


def _vault(tmp_path) -> Vault:
    return Vault(key=b"0" * 16, scope="s", registry_path=str(tmp_path / "reg.db"))


# --- Tests bout-en-bout via Vault (critères 2 et 3) ---


class TestPatronymePrimeSurCommune:
    """Un patronyme déclenché par « M. » ne doit pas repli sur le gazetteer
    communes, même si le token est aussi un nom de commune."""

    @pytest.mark.parametrize("token", ["BOISSEAU", "CHAMPAGNE"])
    def test_token_patronyme_et_commune_rendu_patronyme(self, tmp_path, token: str) -> None:
        v = _vault(tmp_path)
        m = v.mask(f"M. {token}")
        assert m.entities, f"aucune entité détectée pour 'M. {token}'"
        types = [e.type.value for e in m.entities]
        assert all(t == "PATRONYME" for t in types), (
            f"'M. {token}' doit être typé PATRONYME, reçu {types}"
        )

    def test_dupont_patronyme_pur_rendu_patronyme(self, tmp_path) -> None:
        """DUPONT est un patronyme pur (pas une commune): contrôle positif."""
        v = _vault(tmp_path)
        m = v.mask("M. DUPONT")
        assert m.entities
        assert all(e.type.value == "PATRONYME" for e in m.entities)

    def test_substitut_n_est_pas_une_commune(self, tmp_path) -> None:
        """Le substitut d'un patronyme capté par déclencheur ne doit pas être
        un nom issu du gazetteer communes (le dispatch se fait via le cipher
        patronyme, jamais le cipher commune).

        On vérifie que le type enregistré est PATRONYME (garant du dispatch via
        le cipher patronyme) et que le round-trip réussit (preuve de cohérence
        du chiffrement via le gazetteer noms)."""
        v = _vault(tmp_path)
        m = v.mask("M. BOISSEAU")
        assert m.entities
        for e in m.entities:
            assert e.type == EntityType.PATRONYME
            # Le substitut ne doit pas être identique au clair (pas de point fixe).
            assert e.value != "BOISSEAU"


# --- Round-trip (critère de réversibilité) ---


class TestRoundTripPatronyme:
    @pytest.mark.parametrize("token", ["BOISSEAU", "CHAMPAGNE", "DUPONT"])
    def test_unmask_restitue_le_clair(self, tmp_path, token: str) -> None:
        v = _vault(tmp_path)
        original = f"M. {token}"
        masked = v.mask(original)
        restored = v.unmask(masked.text)
        assert restored == original, (
            f"round-trip échoué pour '{original}': '{restored}' != '{original}'"
        )


# --- Test unitaire sur resolve_overlaps (cause racine) ---


class TestArbitragePatronymeCommune:
    """L'arbitrage doit faire gagner PATRONYME sur COMMUNE à confiance et
    longueur égales quand le patronyme est capté par déclencheur contextuel."""

    def test_patronyme_captured_par_gazetteer_nom_gagne_sur_commune(self) -> None:
        """PATRONYME (gazetteer-nom, confiance élevée 0.9, déclencheur présent)
        prime sur COMMUNE (gazetteer-commune, 0.9) chevauchant."""
        patronyme = Span(
            start=3,
            end=11,
            type=EntityType.PATRONYME,
            value="BOISSEAU",
            rule_id="gazetteer-nom",
            confidence=0.9,
        )
        commune = Span(
            start=3,
            end=11,
            type=EntityType.COMMUNE,
            value="BOISSEAU",
            rule_id="gazetteer-commune",
            confidence=0.9,
        )
        resolved = resolve_overlaps([patronyme, commune])
        types = [s.type for s in resolved]
        assert EntityType.PATRONYME in types
        assert EntityType.COMMUNE not in types

    def test_context_capture_ne_prime_pas_sur_commune(self) -> None:
        """``context-capture`` (token inconnu capté par déclencheur, 0.8) NE
        prime pas sur COMMUNE: si le token est aussi une commune, c'est une
        commune légitime et le cipher patronyme ne pourrait pas le chiffrer
        (token absent du gazetteer noms), laissant le span en clair (fuite).
        La commune, qui peut le chiffrer, doit gagner."""
        patronyme = Span(
            start=3,
            end=11,
            type=EntityType.PATRONYME,
            value="SAINT-MICHEL",
            rule_id="context-capture",
            confidence=0.8,
        )
        commune = Span(
            start=3,
            end=11,
            type=EntityType.COMMUNE,
            value="SAINT-MICHEL",
            rule_id="gazetteer-commune",
            confidence=0.9,
        )
        resolved = resolve_overlaps([patronyme, commune])
        types = [s.type for s in resolved]
        assert EntityType.COMMUNE in types
        assert EntityType.PATRONYME not in types

    def test_patronyme_sans_declencheur_perd_contre_commune(self) -> None:
        """Non-régression: sans déclencheur (confidence faible 0.5), le
        comportement par défaut est préservé: COMMUNE (priorité 3) gagne sur
        PATRONYME (priorité 2) à confidence et longueur égales."""
        patronyme = Span(
            start=0,
            end=8,
            type=EntityType.PATRONYME,
            value="BOISSEAU",
            rule_id="gazetteer-nom",
            confidence=0.5,
        )
        commune = Span(
            start=0,
            end=8,
            type=EntityType.COMMUNE,
            value="BOISSEAU",
            rule_id="gazetteer-commune",
            confidence=0.5,
        )
        resolved = resolve_overlaps([patronyme, commune])
        types = [s.type for s in resolved]
        assert EntityType.COMMUNE in types
        assert EntityType.PATRONYME not in types
