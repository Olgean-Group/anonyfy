"""Tests des déclencheurs contextuels (phase 12).

Logique testée:
  - Liste de déclencheurs configurable (M., Mme, Maître, né(e) le, demeurant,
    ci-après) exposée comme ``TRIGGERS``.
  - Détection minimale de candidats par gazetteer (match mot-à-mot contre
    ``load_prenoms()`` / ``load_noms()``) produisant des spans typés
    ``EntityType.PRENOM`` / ``EntityType.PATRONYME``.
  - Un candidat gazetteer SANS déclencheur à proximité a une confiance faible;
    un candidat AVEC déclencheur dans la fenêtre de N caractères a une confiance
    élevée.
  - Un déclencheur capte un nom absent des listes (token capitalisé inconnu mais
    proche d'un déclencheur devient un candidat PATRONYME).
  - Un token capitalisé inconnu des listes et sans déclencheur proche n'est pas
    capté (évite le bruit).

Référence: PLAN.md phase 12, critères 580-584. Décision D20 (frontière
détection/déclencheurs + coquille critère 2 corrigée via .value).
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.detect.context.triggers import EXCLUDED_NOMS, TRIGGERS, apply
from anonyfy.types import EntityType
from anonyfy.vault import UnresolvedSpanError

_FAIBLE = 0.6
_ELEVEE = 0.8


class TestTriggersList:
    def test_contient_declencheurs_exiges(self):
        for t in ("M.", "Mme", "Maître", "né(e) le", "demeurant", "ci-après"):
            assert t in TRIGGERS, f"déclencheur manquant: {t!r}"

    def test_est_iterable_de_chaines(self):
        assert all(isinstance(t, str) for t in TRIGGERS)


class TestApplyPrenoms:
    def test_prenom_gazetteer_sans_trigger_confiance_faible(self):
        spans = apply("Jean")
        jean = [s for s in spans if s.value == "Jean"]
        assert jean, "Jean doit être détecté comme prénom"
        s = jean[0]
        assert s.type == EntityType.PRENOM
        assert s.confidence <= _FAIBLE

    def test_prenom_gazetteer_avec_trigger_confiance_elevee(self):
        spans = apply("M. Jean")
        jean = [s for s in spans if s.value == "Jean"]
        assert jean
        assert jean[0].type == EntityType.PRENOM
        assert jean[0].confidence >= _ELEVEE


class TestApplyNoms:
    def test_nom_gazetteer_sans_trigger_confiance_faible(self):
        spans = apply("Dupont")
        noms = [s for s in spans if s.type == EntityType.PATRONYME and s.value == "Dupont"]
        assert noms, "Dupont doit être détecté comme patronyme"
        assert noms[0].confidence <= _FAIBLE

    def test_nom_gazetteer_avec_trigger_confiance_elevee(self):
        spans = apply("M. Dupont")
        noms = [s for s in spans if s.type == EntityType.PATRONYME and s.value == "Dupont"]
        assert noms
        assert noms[0].confidence >= _ELEVEE


class TestCaptureNomAbsentListes:
    def test_trigger_capture_nom_inconnu(self):
        spans = apply("M. Xyzzqq")
        noms = [s for s in spans if s.type == EntityType.PATRONYME]
        assert noms, "Xyzzqq doit être capté comme nom par le déclencheur M."
        assert noms[0].value == "Xyzzqq"
        assert noms[0].confidence >= _ELEVEE

    def test_sans_trigger_mot_capitalise_inconnu_non_capté(self):
        # Pas de déclencheur, deux tokens inconnus des listes -> aucun span
        # (anti-bruit). NB: « Bonjour » est un vrai patronyme (BONJOUR, 339
        # occurrences) et serait donc légitimement détecté; on utilise des tokens
        # réellement absents des deux gazetteers.
        assert apply("Xyzzqq Zzqqxx") == []


class TestCritere2:
    def test_phrase_complete_renvoie_prenom_ou_nom(self):
        spans = apply("M. Jean Dupont, né le 3 mai 1990")
        assert any(s.type.value in ("PRENOM", "PATRONYME") for s in spans)


class TestFenetre:
    def test_trigger_loin_pas_de_boost(self):
        gap = "x" * 200
        spans = apply(f"M. {gap} Jean")
        jean = [s for s in spans if s.value == "Jean"]
        assert jean
        assert jean[0].confidence <= _FAIBLE

    def test_trigger_apres_candidat_booste_aussi(self):
        spans = apply("Jean, demeurant à Paris")
        jean = [s for s in spans if s.value == "Jean"]
        assert jean
        assert jean[0].confidence >= _ELEVEE


class TestConfiguration:
    def test_triggers_personnalises(self):
        spans = apply("Docteur Jean", triggers=("Docteur",))
        jean = [s for s in spans if s.value == "Jean"]
        assert jean
        assert jean[0].confidence >= _ELEVEE

    def test_aucun_trigger_aucun_boost(self):
        spans = apply("Jean", triggers=())
        jean = [s for s in spans if s.value == "Jean"]
        assert jean
        assert jean[0].confidence <= _FAIBLE


class TestNomsCommunsArbitrage:
    """D25: un nom commun (dans prenoms ET noms) doit produire les deux spans
    PRENOM et PATRONYME pour que l'arbitrage phase 13 puisse décider (priority
    PATRONYME>PRENOM). Le ``elif`` original ne produisait que PRENOM, court-circuitant
    l'arbitrage."""

    def test_nom_commun_avec_trigger_produit_deux_spans(self):
        # ABRAHAM est dans load_noms() ET load_prenoms().
        spans = apply("M. ABRAHAM")
        types = {(s.type, s.value) for s in spans}
        assert (EntityType.PRENOM, "ABRAHAM") in types
        assert (EntityType.PATRONYME, "ABRAHAM") in types

    def test_nom_commun_sans_trigger_produit_deux_spans(self):
        spans = apply("ABRAHAM")
        types = {(s.type, s.value) for s in spans}
        assert (EntityType.PRENOM, "ABRAHAM") in types
        assert (EntityType.PATRONYME, "ABRAHAM") in types


class TestEdge:
    def test_texte_vide(self):
        assert apply("") == []

    def test_offsets_coherents(self):
        text = "M. Jean"
        spans = apply(text)
        for s in spans:
            assert 0 <= s.start < s.end <= len(text)


class TestExcludedNomsR1:
    """Phase 34 — R1 (D34a): ``EXCLUDED_NOMS`` est une liste d'exclusion
    (casefold) scopée PATRONYME : un token dont le casefold y figure n'est
    jamais émis comme PATRONYME, quel que soit le chemin (``gazetteer-nom``
    OU ``context-capture``). Elle ne s'applique pas aux PRENOM (les mots-outils
    ne sont pas des prénoms)."""

    def test_excluded_noms_contient_la_liste_minimale(self):
        for mot in (
            "le", "la", "les", "il", "elle", "nous", "vous", "cette", "ce",
            "ces", "des", "pour", "sur", "dans", "par", "avec", "sans",
            "nir", "siret", "siren", "iban", "tva", "rib",
        ):
            assert mot in EXCLUDED_NOMS, f"mots-outil/acronyme manquant: {mot!r}"

    def test_excluded_noms_casefold(self):
        assert all(isinstance(m, str) and m == m.casefold() for m in EXCLUDED_NOMS)

    @pytest.mark.parametrize("mot", ["le", "la", "siret", "iban"])
    def test_mot_outil_non_emis_patronyme_avec_trigger(self, mot: str) -> None:
        """« M. Le » ne doit pas émettre PATRONYME « Le » (gazetteer-nom boosté
        sinon). « M. Siret » ne doit pas émettre PATRONYME (gazetteer-nom OU
        context-capture)."""
        spans = apply(f"M. {mot.capitalize()}")
        assert not any(
            s.type == EntityType.PATRONYME and s.value.casefold() == mot for s in spans
        ), f"« {mot} » ne doit jamais être émis comme PATRONYME"

    def test_mot_absent_gazetteer_toujours_capte(self):
        """Le filtre d'exclusion n'empêche pas la capture d'un vrai nom inconnu
        des listes par déclencheur (non-régression de la phase 12)."""
        spans = apply("M. Xyzzqq")
        noms = [s for s in spans if s.type == EntityType.PATRONYME]
        assert noms and noms[0].value == "Xyzzqq"


class TestCandidatNuR1:
    """Phase 34 — R1 (D34b/D34c/D34e): un candidat nu (PATRONYME/PRENOM issu du
    seul gazetteer sans déclencheur, confidence < 0.8, rule_id gazetteer-nom /
    gazetteer-prenom / context-capture) n'est pas émis en permissive, reste
    visible en observe (le filtre porte sur le masquage, pas la détection), et
    lève en strict."""

    @pytest.fixture
    def vault(self, tmp_path):
        v = Vault(
            key=b"0" * 16, scope="s", registry_path=str(tmp_path / "reg.db")
        )
        yield v
        v.close()

    @pytest.fixture
    def strict_vault(self, tmp_path):
        v = Vault(
            key=b"0" * 16,
            scope="s",
            policy="strict",
            registry_path=str(tmp_path / "reg.db"),
        )
        yield v
        v.close()

    def test_nom_nu_non_emis_en_permissive(self, vault):
        m = vault.mask("Dupont habite ici")
        assert "Dupont" in m.text, "patronyme nu non masqué attendu en permissive"
        assert not any(e.type == EntityType.PATRONYME for e in m.entities)

    def test_prenom_nu_non_emis_en_permissive(self, vault):
        m = vault.mask("Paul est arrivé")
        assert "Paul" in m.text, "prénom nu non masqué attendu en permissive"
        assert not any(e.type in (EntityType.PATRONYME, EntityType.PRENOM) for e in m.entities)

    def test_nom_nu_visible_en_observe(self, vault):
        m = vault.mask("Dupont", observe=True)
        assert any(s.type == EntityType.PATRONYME for s in m.entities), (
            "observe doit montrer le candidat nu (filtre au masquage, pas à la détection)"
        )

    def test_prenom_nu_visible_en_observe(self, vault):
        m = vault.mask("Paul", observe=True)
        assert any(s.type in (EntityType.PATRONYME, EntityType.PRENOM) for s in m.entities)

    def test_nom_nu_leve_en_strict(self, strict_vault):
        with pytest.raises(UnresolvedSpanError):
            strict_vault.mask("Dupont habite ici")

    def test_prenom_nu_leve_en_strict(self, strict_vault):
        with pytest.raises(UnresolvedSpanError):
            strict_vault.mask("Paul est arrivé hier.")

    def test_nom_declenche_reste_masque_en_permissive(self, vault):
        """Non-régression D34e : un PATRONYME en contexte déclenché (confidence
        0.9 >= 0.8) reste masqué en permissive."""
        m = vault.mask("M. Dupont")
        assert "Dupont" not in m.text
        assert any(e.type == EntityType.PATRONYME for e in m.entities)

    def test_prenom_declenche_reste_masque_en_permissive(self, vault):
        """Non-régression D34e : un PRENOM pur en contexte déclenché (« M. Théo »,
        absent du gazetteer noms) reste masqué en permissive. Seul le prénom nu
        (sans déclencheur) est filtré, pas le prénom déclenché."""
        m = vault.mask("M. Théo")
        assert "Théo" not in m.text
        assert any(e.type == EntityType.PRENOM for e in m.entities)
