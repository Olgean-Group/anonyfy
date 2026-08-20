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

from anonyfy.detect.context.triggers import TRIGGERS, _find_trigger_spans, _near_trigger
from anonyfy.detect.gazetteers.loader import load_communes, load_voies
from anonyfy.types import EntityType, Span

__all__ = ["detect", "detect_communes", "detect_voies"]

# Confiances (cohérent avec phase 12): faible sans déclencheur, élevée avec.
_BASE = 0.5
_BOOSTED = 0.9

# Fenêtre de proximité (caractères) entre déclencheur et candidat.
_WINDOW = 40

# Token: lettres (accentuées), apostrophes ' et ’, tirets internes. Les chiffres
# et la ponctuation séparante ne sont pas des tokens (ex. le "12" et "75001" ne
# font pas partie du nom de voie/commune).
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ'’-]+")

# Nombre maximum de tokens d'une phrase candidate (voies longues, communes
# composées). Borné pour éviter l'explosion combinatoire.
_MAX_WORDS = 8


def _phrase_matches(
    text: str,
    tokens: list[tuple[int, int, str]],
    start_idx: int,
    gazetteer,
) -> tuple[int, int, str] | None:
    """Cherche la plus longue phrase (tokens consécutifs) présente dans le
    gazetteer à partir de ``start_idx``. Renvoie (start, end, matched_value) ou
    None. Les tokens sont joints par une espace et normalisés par casefold.
    """
    best: tuple[int, int, str] | None = None
    words: list[str] = []
    for k in range(start_idx, min(start_idx + _MAX_WORDS, len(tokens))):
        words.append(tokens[k][2])
        phrase = " ".join(words).casefold()
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
    """Détecte les communes et voies dans ``text`` par match gazetteer.

    Renvoie une liste de ``Span`` (``EntityType.COMMUNE`` / ``EntityType.VOIE``)
    avec confiance faible (gazetteer seul) ou élevée (gazetteer + déclencheur).
    Les candidats chevauchants (commune incluse dans une voie plus longue, etc.)
    ne sont pas résolus ici; l'arbitrage est du ressort de ``resolve_overlaps``.
    """
    if not text:
        return []
    if triggers is None:
        triggers = TRIGGERS
    triggers = tuple(triggers)

    communes = load_communes()
    voies = load_voies()
    trigger_spans = _find_trigger_spans(text, triggers)

    tokens: list[tuple[int, int, str]] = [
        (m.start(), m.end(), m.group(0)) for m in _TOKEN_RE.finditer(text)
    ]

    spans: list[Span] = []
    i = 0
    while i < len(tokens):
        # Voie d'abord (souvent plus long): on cherche la plus longue phrase
        # dans chaque gazetteer et on garde la plus longue des deux.
        voie = _phrase_matches(text, tokens, i, voies)
        commune = _phrase_matches(text, tokens, i, communes)
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
            near = _near_trigger(start, end, trigger_spans, window)
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
