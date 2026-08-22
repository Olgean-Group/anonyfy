"""Critere d'acceptation 2: precision >= 95% patronymes en contexte declenche.

La precision (PRD section 10, critere 2) est mesuree sur les patronymes detectes
en contexte declenche (« M. », « Mme », « né(e) le », « demeurant »). On
construit un mini-jeu annoté (decision D12: mesurable sur corpus synthetique pour
la precision, contrairement au rappel) ou l'on connait le resultat attendu:

  - Vrais patronymes (issus du gazetteer SIRENE) en contexte declenche ->
    detectes comme PATRONYME en confiance forte (>= 0.9, confirmee par contexte).
  - Mots communs non-patronymes en contexte declenche (distracteurs) ->
    ne doivent pas etre detectus comme PATRONYME en confiance forte (FP).

Precision = TP / (TP + FP) sur les spans PATRONYME de confiance >= 0.9
(contexte declenche confirmé). Cible >= 0.95.

La detection phase 12/13 confirme le contexte: un span PATRONYME atteint 0.9
uniquement si le mot est dans le gazetteer ET un declencheur contextuel fort est
present (« M. », « né(e) le », « demeurant »). Sans gazetteer, le span reste a
0.8 (faible, non confirme) et est exclue du decomte de precision sur contexte
declenche.

Reference: PRD section 10 critere 2, PLAN.md phase 19, decision D12.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import load_noms
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "acceptance-precision"
_TARGET = 0.95
_TRIGGERS = ("M. ", "Mme ", "né le ", "née le ", "demeurant ")

# Seuil de confiance « contexte declenche confirme » (phase 17, D27): un span
# PATRONYME avec confidence >= _TRIGGERED_CONF est confirme par un declencheur
# contextuel fort (« M. », « né(e) le », « demeurant »). En dessous, le span est
# non confirme (0.8 = capitalise apres « M. » mais absent du gazetteer) et exclue
# du decomte de precision sur contexte declenche.
_TRIGGERED_CONF = 0.9


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


def _load_real_patronymes() -> set[str]:
    """Patronymes du gazetteer SIRENE (forme majuscule)."""
    return {e.name for e in load_noms()}


# Patronymes reels du gazetteer detectes comme PATRONYME (pas confondus avec
# COMMUNE/VOIE). Verifies empiriquement (phase 13).
_REAL_PATRONYMES: tuple[str, ...] = (
    "Dupont",
    "Martin",
    "Leroy",
    "Dubois",
    "Caulier",
    "Bureau",
    "Petit",
    "Richard",
    "Moreau",
    "Lefebvre",
    "Garcia",
    "Fournier",
    "Girard",
    "Mercier",
    "Henry",
    "Gauthier",
    "Vincent",
    "Lopez",
    "Chevalier",
    "Clement",
    "Delorme",
)

# Mots communs non-patronymes (absents du gazetteer) utilises comme distracteurs
# en contexte declenche. Aucun ne doit atteindre la confiance _TRIGGERED_CONF
# en tant que PATRONYME (sinon FP). Phase 27 OBJ-REC-108: distracteurs mis à
# jour pour le gazetteer INSEE complet (879k noms) — « Patient », « Docteur »,
# « Service » etc. sont désormais des patronymes réels du gazetteer.
_DISTRACTORS: tuple[str, ...] = (
    "Directeur",
    "Infirmier",
    "Radiologue",
    "Cardiologue",
    "Urgence",
    "Stagiaire",
    "Apprenti",
    "Beneficiaire",
    "Usager",
    "Convalescent",
)


def _triggered_contexts(word: str) -> tuple[str, ...]:
    """Construit des phrases avec `word` en contexte declenche."""
    return (
        f"M. {word} est venu.",
        f"née le 3 mai 1990, M. {word}",
        f"demeurant 12 rue Pasteur, M. {word}",
    )


def _detected_triggered_patronymes(vault, text: str) -> list[str]:
    """Valeurs des spans PATRONYME de confiance >= _TRIGGERED_CONF dans `text`."""
    m = vault.mask(text, observe=True)
    return [
        s.value
        for s in m.entities
        if s.type is EntityType.PATRONYME and s.confidence >= _TRIGGERED_CONF
    ]


def test_precision_patronymes_contexte_declenche(vault):
    """Precision >= 0.95 sur les patronymes en contexte declenche (mini-jeu, D12).

    TP = span PATRONYME (conf >= 0.9) dont la valeur est un patronyme du
    gazetteer. FP = span PATRONYME (conf >= 0.9) dont la valeur n'est PAS un
    patronyme du gazetteer. Precision = TP / (TP + FP).
    """
    gazetteer = _load_real_patronymes()

    true_pos = 0
    false_pos = 0
    for word in _REAL_PATRONYMES:
        for text in _triggered_contexts(word):
            for val in _detected_triggered_patronymes(vault, text):
                if val.upper() in gazetteer:
                    true_pos += 1
                else:
                    false_pos += 1

    for word in _DISTRACTORS:
        for text in _triggered_contexts(word):
            for val in _detected_triggered_patronymes(vault, text):
                if val.upper() in gazetteer:
                    true_pos += 1
                else:
                    false_pos += 1

    total = true_pos + false_pos
    assert total > 0, "aucun span PATRONYME en confiance declenchee: mini-jeu vide"
    precision = true_pos / total
    assert precision >= _TARGET, (
        f"precision patronymes {precision:.4f} < {_TARGET} (TP={true_pos}, FP={false_pos})"
    )


def test_distracteurs_non_patronymes_pas_de_fp_conf_forte(vault):
    """Garde-fou: aucun mot commun non-patronyme n'atteint la confiance
    declenchee (>= 0.9) en tant que PATRONYME (FP = 0 sur les distracteurs)."""
    gazetteer = _load_real_patronymes()
    for word in _DISTRACTORS:
        assert word.upper() not in gazetteer, (
            f"distracteur {word!r} est dans le gazetteer: mini-jeu invalide"
        )
        for text in _triggered_contexts(word):
            for val in _detected_triggered_patronymes(vault, text):
                # Un span PATRONYME conf >= 0.9 sur un non-patronyme est un FP.
                pytest.fail(
                    f"FP conf fort: {val!r} (distracteur {word!r}) detecte "
                    f"PATRONYME conf>= {_TRIGGERED_CONF} dans {text!r}"
                )
