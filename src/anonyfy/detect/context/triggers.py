"""Déclencheurs contextuels et détection minimale de candidats noms/prénoms.

Détection par gazetteer (match mot-à-mot, insensible à la casse, aux frontières
de tokens) contre ``load_prenoms()`` / ``load_noms()`` (phase 09). Chaque candidat
est un ``Span`` typé ``EntityType.PRENOM`` ou ``EntityType.PATRONYME``.

Confiance:
  - Candidat gazetteer SANS déclencheur à proximité: faible (``_BASE``).
  - Candidat gazetteer AVEC déclencheur dans la fenêtre: élevée (``_BOOSTED``).
  - Token capitalisé inconnu des listes AVEC déclencheur à proximité: capté
    comme ``PATRONYME`` avec confiance élevée (``_CAPTURED``). Sans déclencheur,
    il n'est pas capté (anti-bruit).

La liste ``TRIGGERS`` est configurable et peut être surchargée par l'appelant via
le paramètre ``triggers`` de ``apply``. ``window`` (caractères) contrôle la
proximité admise entre un déclencheur et un candidat.

L'arbitrage final (résolution des chevauchements multi-types) relève de la
phase 13 (hors périmètre): ``apply`` renvoie la liste brute des candidats, sans
dédoublonnage ni résolution.

Référence: PLAN.md phase 12, critères 580-584. Décision D20.
"""

from __future__ import annotations

import re

from anonyfy.detect.gazetteers.loader import load_noms, load_prenoms
from anonyfy.types import EntityType, Span

__all__ = ["TRIGGERS", "apply"]

#: Déclencheurs contextuels par défaut (PLAN §Phase 12).
TRIGGERS: tuple[str, ...] = (
    "M.",
    "Mme",
    "Maître",
    "né(e) le",
    "demeurant",
    "ci-après",
)

# Confidences (PRD §7 plafond): faible sans déclencheur, élevée avec.
_BASE = 0.5
_BOOSTED = 0.9
_CAPTURED = 0.8

# Fenêtre de proximité (caractères) entre déclencheur et candidat.
_WINDOW = 40

# Token candidat: mot capitalisé, lettres accentuées, apostrophes/tirets internes
# (Jean-Marc, O'Brien). Frontières par exclusion des caractères non lettres.
_TOKEN_RE = re.compile(r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'’-]*")


def _find_trigger_spans(text: str, triggers: tuple[str, ...]) -> list[tuple[int, int]]:
    """Positions (start, end) de chaque occurrence de déclencheur dans ``text``."""
    positions: list[tuple[int, int]] = []
    for t in triggers:
        if not t:
            continue
        start = 0
        while True:
            i = text.find(t, start)
            if i < 0:
                break
            positions.append((i, i + len(t)))
            start = i + len(t)
    return positions


def _overlaps_trigger(
    tok_start: int,
    tok_end: int,
    trigger_spans: list[tuple[int, int]],
) -> bool:
    """True si le token chevauche une occurrence de déclencheur.

    Évite de capturer comme candidat la partie lettrée d'un déclencheur lui-même
    (ex. le « M » de « M. », le « Mme » de « Mme »).
    """
    for ts, te in trigger_spans:
        if tok_start < te and ts < tok_end:
            return True
    return False


def _near_trigger(
    tok_start: int,
    tok_end: int,
    trigger_spans: list[tuple[int, int]],
    window: int,
) -> bool:
    """True si un déclencheur est à ``window`` caractères ou moins du token."""
    for ts, te in trigger_spans:
        if tok_end <= ts:
            if ts - tok_end <= window:
                return True
        elif te <= tok_start:
            if tok_start - te <= window:
                return True
        else:
            # Chevauchement (token sur le déclencheur, ex. « M. » sur « M »).
            return True
    return False


def apply(
    text: str,
    triggers: tuple[str, ...] | list[str] | None = None,
    window: int = _WINDOW,
) -> list[Span]:
    """Détecte les candidats prénom/nom dans ``text`` et applique les déclencheurs.

    Renvoie une liste de ``Span`` (``EntityType.PRENOM`` / ``EntityType.PATRONYME``)
    avec confiance faible (gazetteer seul) ou élevée (gazetteer + déclencheur, ou
    token inconnu capté par déclencheur). ``triggers=None`` utilise ``TRIGGERS``.
    """
    if not text:
        return []
    if triggers is None:
        triggers = TRIGGERS
    triggers = tuple(triggers)

    prenoms = load_prenoms()
    noms = load_noms()
    trigger_spans = _find_trigger_spans(text, triggers)

    spans: list[Span] = []
    for m in _TOKEN_RE.finditer(text):
        value = m.group(0)
        key = value.casefold()
        tok_start, tok_end = m.start(), m.end()
        # Un token chevauchant un déclencheur (ex. « M » dans « M. ») est la
        # partie lettrée du déclencheur lui-même, pas un candidat nom.
        if _overlaps_trigger(tok_start, tok_end, trigger_spans):
            continue
        near = _near_trigger(tok_start, tok_end, trigger_spans, window)

        if key in prenoms:
            spans.append(
                Span(
                    start=tok_start,
                    end=tok_end,
                    type=EntityType.PRENOM,
                    value=value,
                    rule_id="gazetteer-prenom",
                    confidence=_BOOSTED if near else _BASE,
                )
            )
        elif key in noms:
            spans.append(
                Span(
                    start=tok_start,
                    end=tok_end,
                    type=EntityType.PATRONYME,
                    value=value,
                    rule_id="gazetteer-nom",
                    confidence=_BOOSTED if near else _BASE,
                )
            )
        elif near:
            # Nom absent des listes, capté par un déclencheur contextuel.
            spans.append(
                Span(
                    start=tok_start,
                    end=tok_end,
                    type=EntityType.PATRONYME,
                    value=value,
                    rule_id="context-capture",
                    confidence=_CAPTURED,
                )
            )
    return spans
