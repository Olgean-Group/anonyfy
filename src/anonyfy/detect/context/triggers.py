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

import bisect
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


def _prepare_triggers(
    trigger_spans: list[tuple[int, int]],
) -> tuple[list[int], list[int], list[int]]:
    """Précalcule les structures triées pour les tests de chevauchement/proximité.

    Renvoie (starts, ends, max_te_prefix) triés par ``start`` croissant.
    ``max_te_prefix[j]`` = max des ``end`` des ``j`` premiers triggers (0 pour
    j=0), utilisé pour répondre en O(log n) aux tests de chevauchement et de
    proximité sans parcourir tous les triggers.
    """
    if not trigger_spans:
        return [], [], [0]
    ordered = sorted(trigger_spans)
    starts = [s for s, _ in ordered]
    ends = [e for _, e in ordered]
    max_te_prefix = [0]
    cur = 0
    for e in ends:
        if e > cur:
            cur = e
        max_te_prefix.append(cur)
    return starts, ends, max_te_prefix


def _overlaps_trigger(
    tok_start: int,
    tok_end: int,
    trig_starts: list[int],
    trig_max_te_prefix: list[int],
) -> bool:
    """True si le token chevauche une occurrence de déclencheur (O(log n)).

    Un chevauchement existe ssi un trigger a ``start < tok_end`` ET ``end >
    tok_start``. Les triggers étant triés par ``start``, ``bisect`` isole ceux à
    gauche (start < tok_end) et ``max_te_prefix`` borne leur plus grand ``end``.
    """
    j = bisect.bisect_left(trig_starts, tok_end)
    return j > 0 and trig_max_te_prefix[j] > tok_start


def _near_trigger(
    tok_start: int,
    tok_end: int,
    trig_starts: list[int],
    trig_max_te_prefix: list[int],
    window: int,
) -> bool:
    """True si un déclencheur est à ``window`` caractères ou moins du token (O(log n)).

    Côté droit (start >= tok_end): near ssi un start <= tok_end + window.
    Côté gauche (start < tok_end): near ssi un end > tok_start - window (cela
    couvre le chevauchement et la proximité avant).
    """
    j = bisect.bisect_left(trig_starts, tok_end)
    if j < len(trig_starts) and trig_starts[j] <= tok_end + window:
        return True
    return j > 0 and trig_max_te_prefix[j] > tok_start - window


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
    trig_starts, _trig_ends, trig_max_te = _prepare_triggers(trigger_spans)

    spans: list[Span] = []
    for m in _TOKEN_RE.finditer(text):
        value = m.group(0)
        key = value.casefold()
        tok_start, tok_end = m.start(), m.end()
        # Un token chevauchant un déclencheur (ex. « M » dans « M. ») est la
        # partie lettrée du déclencheur lui-même, pas un candidat nom.
        if _overlaps_trigger(tok_start, tok_end, trig_starts, trig_max_te):
            continue
        near = _near_trigger(tok_start, tok_end, trig_starts, trig_max_te, window)

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
        if key in noms:
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
        if key not in prenoms and key not in noms and near:
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
