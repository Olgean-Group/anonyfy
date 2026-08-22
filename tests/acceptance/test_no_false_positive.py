"""Phase 34 — R1 : aucun faux positif patronyme/prénom (mots-outils en initiale).

Le gazetteer noms (879 421 entrées) contient des mots-outils (« Le », « La »,
« Il », « Nous », « Cette », « SIRET », « IBAN »...) qui se déclenchent sur la
seule majuscule d'initiale de phrase ou un déclencheur adjacent, faisant perdre
son premier mot à chaque phrase. R1 corrige (PLAN.md phase 34) :

- ``EXCLUDED_NOMS`` (casefold, D34a) : un token dont le casefold est dans la
  liste n'est JAMAIS émis comme PATRONYME, quel que soit le chemin
  (``gazetteer-nom`` OU ``context-capture``) — OBJ-010. La liste est scopée
  PATRONYME (les mots-outils ne sont pas des prénoms).
- Le filtrage des candidats nus (PATRONYME/PRENOM issus du seul gazetteer sans
  déclencheur, confidence < 0.8) au niveau du masquage non-observe (D34b/D34c) :
  en permissive, le premier mot de phrase n'est plus masqué ; en strict, il
  lève ; en observe, il reste visible.

Ce test masque un corpus de phrases administratives variées SANS données
personnelles (conjonctions, prépositions, pronoms, adverbes en initiale) et
vérifie que le texte de sortie est identique à l'entrée (aucun mot masqué,
premier mot préservé), y compris un prénom nu en initiale (« Paul est arrivé
hier. », OBJ-007).

Référence: PLAN.md phase 34, critères d'acceptation 2-6 (D34a-D34e).
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.detect.context.triggers import EXCLUDED_NOMS
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "acceptance-no-false-positive"

# Corpus administratif sans données personnelles : les 5 phrases de la recette
# R1 + des initiales variées (pronoms, prépositions, conjonctions, adverbes).
# Chaque phrase ne contient aucun span COMMUNE/VOIE/CP/FPE (vérifié : seul le
# gazetteer noms/prénoms y répond, hors périmètre R1).
CORPUS: tuple[str, ...] = (
    # 5 phrases de la recette R1 (premier mot masqué à tort avant R1).
    "Le contrat prend effet le premier jour du mois.",
    "La société doit fournir une facture conforme.",
    "Il faut relire la clause de confidentialité.",
    "Nous avons livré le rapport hier soir.",
    "Cette base de données contient trois millions de lignes.",
    # Prénom nu en initiale sans déclencheur (OBJ-006/OBJ-007) : non masqué en
    # permissive (filtre D34e), levé en strict.
    "Paul est arrivé hier.",
    # Autres initiales variées.
    "Notre équipe a terminé le dossier.",
    "Leur réponse est arrivée hier.",
    "Tout est conforme aux exigences.",
    "Bien reçu, merci pour votre retour.",
    "Depuis hier, le système est stable.",
    "Entre deux réunions, le temps manque.",
    "Sous réserve de validation, l'affaire est close.",
    "Voici le rapport demandé.",
    "Cependant, il faut vérifier les chiffres.",
    "Je confirme la réception de votre message.",
    "Quand le dossier sera complet, nous relancerons.",
    "Si le paiement est reçu, la commande part.",
    "Mais il faut d'abord vérifier les informations.",
    "Ensuite, il faudra relire l'ensemble.",
    "Puis nous archiverons le dossier.",
    "Aussi faut-il prévoir une marge de temps.",
    "Chaque demande est étudiée avec attention.",
    "Toutefois, le délai reste court.",
    "Enfin, nous avons terminé la vérification.",
    "Quant au contrat, il a été signé.",
    "Voilà pourquoi nous avons décalé le rendez-vous.",
    "Heureusement, le système a été rétabli.",
    "Une pièce jointe accompagne cet envoi.",
    "Merci d'avance pour votre diligence.",
)


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


@pytest.fixture
def strict_vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, policy="strict", registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


def _phrases_ids() -> list[str]:
    return [f"ph{idx}" for idx in range(len(CORPUS))]


class TestCorpusSansFalsePositive:
    """Critère 2 : en permissive, le texte masqué est identique à l'entrée."""

    @pytest.mark.parametrize("phrase", CORPUS, ids=_phrases_ids())
    def test_texte_inchange_en_permissive(self, vault, phrase: str) -> None:
        m = vault.mask(phrase)
        assert m.text == phrase, (
            f"faux positif en permissive : {m.text!r} != {phrase!r}. "
            f"Le premier mot (ou un mot) a été masqué sans déclencheur."
        )

    def test_prenom_nu_en_observe_reste_visible(self, vault) -> None:
        """D34b : observe voit encore les candidats nus (non filtrés en
        observation) — le filtre porte sur le masquage, pas la détection."""
        m = vault.mask("Paul est arrivé hier.", observe=True)
        assert any(s.value.casefold() == "paul" for s in m.entities), (
            "« Paul » (candidat nu) doit rester visible en mode observe"
        )

    def test_prenom_nu_leve_en_strict(self, strict_vault) -> None:
        """Critère 6 : en strict, un prénom nu sans déclencheur lève."""
        with pytest.raises(Exception):
            strict_vault.mask("Paul est arrivé hier.")
        # NB: la classe précise UnresolvedSpanError est vérifiée dans
        # tests/unit/context/test_triggers.py (contexte unitaire).


class TestExcludedNoms:
    """Critères 3 et 4 (D34a, OBJ-006/OBJ-010) : EXCLUDED_NOMS est un filtre
    global PATRONYME — un token dont le casefold est dans la liste n'est JAMAIS
    émis comme PATRONYME, même avec un déclencheur proche."""

    @pytest.mark.parametrize(
        "mot", sorted(EXCLUDED_NOMS), ids=lambda m: f"exclu-{m}"
    )
    def test_mot_outil_jamais_emission_patronyme(self, vault, mot: str) -> None:
        # Avec déclencheur « M. » : le token serait sinon PATRONYM (gazetteer-nom
        # boosté à 0.9 s'il est dans le gazetteer noms, ou context-capture à 0.8
        # s'il en est absent). Il ne doit JAMAIS être émis comme PATRONYM.
        forme = mot.capitalize()
        spans = vault.mask(f"M. {forme}", observe=True).entities
        assert not any(
            s.type == EntityType.PATRONYME and s.value.casefold() == mot for s in spans
        ), f"« {forme} » ne doit jamais être émis comme PATRONYME (dans EXCLUDED_NOMS)"

    def test_nir_siret_siren_iban_non_masques_comme_patronyme(self, vault) -> None:
        """Critère 4 (OBJ-010) : les acronymes du domaine ne sont jamais émis
        comme PATRONYME, y compris en contexte déclenché (M.) où ils seraient
        sinon captés via gazetteer-nom boosté ou context-capture.

        NB : le contrat porte sur le TYPAGE PATRONYME (D34a scopé
        PATRONYME). « IBAN » figure aussi dans le gazetteer prénoms : en
        contexte déclenché il reste un PRENOM légitime (D34e) — hors périmètre
        de l'exclusion PATRONYME — donc on n'exige pas que le label reste
        littéralement dans le texte, seulement qu'il ne soit jamais typé
        PATRONYME."""
        for label, numero in (
            ("NIR", "1234567890123 89"),
            ("SIRET", "73282932000033"),
            ("SIREN", "732829320"),
            ("IBAN", "FR7630006000011234567890189"),
        ):
            m = vault.mask(f"M. {label} {numero}")
            assert not any(
                s.type == EntityType.PATRONYME and s.value.casefold() == label.casefold()
                for s in m.entities
            ), f"{label} ne doit jamais être émis comme PATRONYME: {m.entities!r}"

    def test_siret_en_contexte_declenche_non_masque(self, vault) -> None:
        """Critère 4 (PLAN): cas explicite « M. SIRET 73282932000033 » — le
        label « SIRET » (absent du gazetteer prénoms) reste dans le texte :
        aucun chemin ne doit le masquer (ni gazetteer-nom boosté, ni
        context-capture)."""
        m = vault.mask("M. SIRET 73282932000033")
        assert "SIRET" in m.text, f"SIRET masqué en contexte déclenché: {m.text!r}"
        assert not any(
            s.type == EntityType.PATRONYME and s.value.casefold() == "siret"
            for s in m.entities
        )

    def test_siret_seul_non_masque_comme_patronyme(self, vault) -> None:
        """« SIRET » nu (sans numéro) n'est pas masqué comme patronyme."""
        m = vault.mask("SIRET 73282932000033")
        assert "SIRET" in m.text
