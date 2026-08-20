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

from anonyfy.detect.context.triggers import TRIGGERS, apply
from anonyfy.types import EntityType

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
