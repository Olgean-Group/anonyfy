"""Détection des communes et voies par gazetteer (phase 13).

Étend la détection phase 12 (prenoms/noms) aux communes (``load_communes``) et
voies (``load_voies``). Match de phrases multi-mots contre les gazetteers,
insensible à la casse (casefold), avec offsets et confiance. Mécanisme minimal:
pas de fuzzy, pas de stemming, pas de résolution d'homonymes (PRD §7 plafond de
faux positifs accepté; mode observation phase 17 pour le découvrir).

Confiance:
  - Candidat gazetteer SANS déclencheur à proximité: faible (``_BASE``).
  - Candidat gazetteer AVEC déclencheur dans la fenêtre: élevée (``_BOOSTED``).

L'arbitrage final (résolution des chevauchements multi-types) relève de la
phase 13 (``resolve_overlaps``); ``detect`` renvoie la liste brute des candidats.

Référence: PLAN.md phase 13, décision D20 (pré-autorisation détection communes/voies).
"""

from __future__ import annotations

import re

from anonyfy.detect.context.triggers import (
    TRIGGERS,
    _find_trigger_spans,
    _near_trigger,
    _prepare_triggers,
)
from anonyfy.detect.gazetteers.loader import load_communes, load_voies
from anonyfy.detect.validators import cp as cp_val
from anonyfy.types import EntityType, Span

__all__ = ["detect", "detect_communes", "detect_voies"]

# Confiances (cohérent avec phase 12): faible sans déclencheur, élevée avec.
_BASE = 0.5
_BOOSTED = 0.9

# Fenêtre de proximité (caractères) entre déclencheur et candidat.
_WINDOW = 40

# Phase 30 — S4: déclencheurs CP (OBJ-REC-109). Un CP est masqué s'il est
# adjacent à une commune détectée OU précédé d'un de ces déclencheurs.
_CP_TRIGGERS: tuple[str, ...] = ("à ", "demeurant à ", "habite à ")

# Fenêtre de proximité entre un CP et une commune (caractères de l'interspace).
_CP_COMMUNE_WINDOW = 15

# Fenêtre entre la fin d'un déclencheur CP et le début du CP.
_CP_TRIGGER_WINDOW = 10

# Token: lettres (accentuées), apostrophes ' et ’, tirets internes. Les chiffres
# et la ponctuation séparante ne sont pas des tokens (ex. le "12" et "75001" ne
# font pas partie du nom de voie/commune).
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ'’-]+")

# Nombre maximum de tokens d'une phrase candidate (voies longues, communes
# composées). Borné pour éviter l'explosion combinatoire.
_MAX_WORDS = 8


def _phrase_matches(
    tokens: list[tuple[int, int, str]],
    cfold_tokens: list[str],
    start_idx: int,
    gazetteer,
) -> tuple[int, int, str] | None:
    """Cherche la plus longue phrase (tokens consécutifs) présente dans le
    gazetteer à partir de ``start_idx``. Renvoie (start, end, matched_value) ou
    None. Les tokens sont joints par une espace et normalisés par casefold.

    ``cfold_tokens`` est la version pré-casefold des valeurs (calculée une fois
    par ``detect``) pour éviter de recasefold la phrase entière à chaque
    extension.
    """
    best: tuple[int, int, str] | None = None
    # Phase 32 — M4: court-circuit si le premier token ne peut demarrer aucune
    # entree du gazetteer (prefiltre first_words). Evite ~8 joins + lookups pour
    # les tokens non pertinents (la majorite dans un texte administratif).
    if cfold_tokens[start_idx] not in gazetteer.first_words:
        return best
    cfold_words: list[str] = []
    words: list[str] = []
    for k in range(start_idx, min(start_idx + _MAX_WORDS, len(tokens))):
        words.append(tokens[k][2])
        cfold_words.append(cfold_tokens[k])
        phrase = " ".join(cfold_words)
        if phrase in gazetteer:
            best = (tokens[start_idx][0], tokens[k][1], " ".join(words))
        # Continue à étendre même après un match: le nom le plus long gagne
        # (ex. "rue de la Paix" > "rue").
    return best


def detect(
    text: str,
    triggers: tuple[str, ...] | list[str] | None = None,
    window: int = _WINDOW,
) -> list[Span]:
    """Détecte les communes, voies et CP couplés dans ``text`` par match gazetteer.

    Renvoie une liste de ``Span`` (``EntityType.COMMUNE`` / ``EntityType.VOIE`` /
    ``EntityType.CODE_POSTAL``) avec confiance faible (gazetteer seul) ou élevée
    (gazetteer + déclencheur, ou CP couplé). Les candidats chevauchants ne sont
    pas résolus ici; l'arbitrage est du ressort de ``resolve_overlaps``.

    Phase 30 — S4 (OBJ-REC-109): les CP (5 chiffres) ne sont émis QUE s'ils
    sont adjacents à une commune détectée ou précédés d'un déclencheur CP
    (``à ``, ``demeurant à ``, ``habite à ``). Un nombre isolé n'est pas émis.
    """
    if not text:
        return []
    if triggers is None:
        triggers = TRIGGERS
    triggers = tuple(triggers)

    communes = load_communes()
    voies = load_voies()
    trigger_spans = _find_trigger_spans(text, triggers)
    trig_starts, _trig_ends, trig_max_te = _prepare_triggers(trigger_spans)

    tokens: list[tuple[int, int, str]] = [
        (m.start(), m.end(), m.group(0)) for m in _TOKEN_RE.finditer(text)
    ]
    cfold_tokens = [v.casefold() for (_, _, v) in tokens]

    spans: list[Span] = []
    i = 0
    while i < len(tokens):
        # Voie d'abord (souvent plus long): on cherche la plus longue phrase
        # dans chaque gazetteer et on garde la plus longue des deux.
        voie = _phrase_matches(tokens, cfold_tokens, i, voies)
        commune = _phrase_matches(tokens, cfold_tokens, i, communes)
        chosen: tuple[int, int, str, EntityType] | None = None
        if voie is not None and commune is not None:
            if (voie[1] - voie[0]) >= (commune[1] - commune[0]):
                chosen = (*voie, EntityType.VOIE)
            else:
                chosen = (*commune, EntityType.COMMUNE)
        elif voie is not None:
            chosen = (*voie, EntityType.VOIE)
        elif commune is not None:
            chosen = (*commune, EntityType.COMMUNE)

        if chosen is not None:
            start, end, value, etype = chosen
            near = _near_trigger(start, end, trig_starts, trig_max_te, window)
            rule = "gazetteer-voie" if etype == EntityType.VOIE else "gazetteer-commune"
            spans.append(
                Span(
                    start=start,
                    end=end,
                    type=etype,
                    value=value,
                    rule_id=rule,
                    confidence=_BOOSTED if near else _BASE,
                )
            )
            # Avancer au-delà du match (ne pas re-matcher les tokens couverts).
            # Trouver l'indice du premier token après ``end``.
            i = _token_index_after(tokens, end)
        else:
            i += 1

    # Phase 30 — S4: couplage CP/commune (OBJ-REC-109).
    commune_spans = [s for s in spans if s.type == EntityType.COMMUNE]
    spans.extend(_detect_coupled_cps(text, commune_spans))
    return spans


def _token_index_after(tokens: list[tuple[int, int, str]], pos: int) -> int:
    """Indice du premier token dont le début est >= ``pos`` (recherche linéaire)."""
    for idx, (s, _e, _v) in enumerate(tokens):
        if s >= pos:
            return idx
    return len(tokens)


def detect_communes(
    text: str,
    triggers: tuple[str, ...] | list[str] | None = None,
    window: int = _WINDOW,
) -> list[Span]:
    """Détecte uniquement les communes (sous-ensemble de ``detect``)."""
    return [s for s in detect(text, triggers, window) if s.type == EntityType.COMMUNE]


def detect_voies(
    text: str,
    triggers: tuple[str, ...] | list[str] | None = None,
    window: int = _WINDOW,
) -> list[Span]:
    """Détecte uniquement les voies (sous-ensemble de ``detect``)."""
    return [s for s in detect(text, triggers, window) if s.type == EntityType.VOIE]


# --- Phase 30 — S4: couplage CP / commune (OBJ-REC-109) -------------------


def _cp_near_commune(
    cp_start: int,
    cp_end: int,
    commune_spans: list[Span],
    window: int = _CP_COMMUNE_WINDOW,
) -> bool:
    """True si le CP est adjacent (<= ``window`` caractères) à une commune.

    L'adjacence est mesurée par l'écart entre le CP et la commune (avant ou
    après). Un CP collé à une commune (« 16000 Angoulême ») a un écart de 1
    (l'espace); on accepte jusqu'à ``window`` caractères d'interstice.
    """
    for c in commune_spans:
        gap = max(c.start - cp_end, cp_start - c.end)
        if 0 <= gap <= window:
            return True
    return False


def _cp_after_trigger(
    cp_start: int,
    text: str,
    triggers: tuple[str, ...] = _CP_TRIGGERS,
    window: int = _CP_TRIGGER_WINDOW,
) -> bool:
    """True si un déclencheur CP se termine dans ``window`` chars avant le CP."""
    for trigger in triggers:
        if not trigger:
            continue
        search_from = 0
        while True:
            idx = text.find(trigger, search_from)
            if idx < 0:
                break
            trigger_end = idx + len(trigger)
            if 0 <= cp_start - trigger_end <= window:
                return True
            search_from = idx + 1
    return False


def _detect_coupled_cps(
    text: str,
    commune_spans: list[Span],
) -> list[Span]:
    """Détecte les CP couplés à une commune ou après un déclencheur (OBJ-REC-109).

    Un CP (5 chiffres) n'est émis que s'il est adjacent à une commune détectée
    OU précédé d'un déclencheur CP (``à ``, ``demeurant à ``, ``habite à ``).
    Les CP isolés ne sont pas émis (anti faux positifs sur nombres à 5 chiffres).
    """
    raw_cps = cp_val.detect(text)
    coupled: list[Span] = []
    for cp in raw_cps:
        near_commune = _cp_near_commune(cp.start, cp.end, commune_spans)
        triggered = _cp_after_trigger(cp.start, text)
        if not near_commune and not triggered:
            continue
        rule = "cp-commune" if near_commune else "cp-trigger"
        coupled.append(
            Span(
                start=cp.start,
                end=cp.end,
                type=EntityType.CODE_POSTAL,
                value=cp.value,
                rule_id=rule,
                confidence=_BOOSTED,
            )
        )
    return coupled
