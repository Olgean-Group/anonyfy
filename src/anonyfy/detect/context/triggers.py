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

__all__ = ["EXCLUDED_NOMS", "TRIGGERS", "apply"]

#: Déclencheurs contextuels par défaut (PLAN §Phase 12).
TRIGGERS: tuple[str, ...] = (
    "M.",
    "Mme",
    "Maître",
    "né(e) le",
    "demeurant",
    "ci-après",
)

#: Mots-outils et acronymes du domaine exclus du typage PATRONYME (phase 34,
#: D34a/OBJ-010). Le gazetteer noms (879 421 entrées SIRENE) contient des mots
#: grammaticaux français (« Le », « La », « Il », « Nous », « Cette »...) qui se
#: déclenchent sur la seule majuscule d'initiale de phrase (chaque phrase perdait
#: son premier mot) et des acronymes du domaine (NIR, SIRET, SIREN, IBAN, TVA,
#: RIB) masqués comme patronymes. Un token dont le casefold est dans cette liste
#: n'est JAMAIS émis comme PATRONYME, quel que soit le chemin (``gazetteer-nom``
#: OU ``context-capture``). La liste est scopée PATRONYME : elle ne s'applique
#: pas aux PRENOM (les mots-outils ne sont pas des prénoms ; le filtrage PRENOM
#: repose sur l'absence de déclencheur, D34b).
EXCLUDED_NOMS: frozenset[str] = frozenset(
    {
        # Déterminants / pronoms (mots-outils du gazetteer noms).
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "ce",
        "cet",
        "cette",
        "ces",
        "il",
        "elle",
        "ils",
        "elles",
        "je",
        "nous",
        "vous",
        "mon",
        "ma",
        "mes",
        "ton",
        "ta",
        "tes",
        "son",
        "sa",
        "ses",
        "notre",
        "votre",
        "leur",
        "leurs",
        # Prépositions / conjonctions.
        "pour",
        "sur",
        "dans",
        "par",
        "avec",
        "sans",
        "sous",
        "vers",
        "chez",
        "hors",
        "selon",
        "parmi",
        "contre",
        "entre",
        "depuis",
        "avant",
        "après",
        "durant",
        "dès",
        "et",
        "ou",
        "mais",
        "donc",
        "or",
        "ni",
        "car",
        "si",
        "quand",
        "lorsque",
        "comme",
        "qui",
        "que",
        "quoi",
        "dont",
        "où",
        # Adverbes et locutions courantes en initiale de phrase administrative.
        "tout",
        "toute",
        "tous",
        "toutes",
        "bien",
        "très",
        "plus",
        "moins",
        "beaucoup",
        "peu",
        "assez",
        "aussi",
        "encore",
        "déjà",
        "jamais",
        "souvent",
        "toujours",
        "mieux",
        "enfin",
        "ensuite",
        "puis",
        "pendant",
        "alors",
        "voici",
        "voilà",
        "cependant",
        "toutefois",
        "quant",
        "heureusement",
        "merci",
        "oui",
        "non",
        "chaque",
        "aucun",
        "aucune",
        "autre",
        "autres",
        "même",
        # Acronymes du domaine (labels de types structurés, OBJ-010).
        "nir",
        "siret",
        "siren",
        "iban",
        "tva",
        "rib",
    }
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

#: Nombre maximum de tokens d'un patronyme composé (phase 35, D35e). Les
#: entrées multi-mots du gazetteer noms (220 200) vont jusqu'à ~8 mots; borné à
#: 3 pour la détection des composés courants (recette S1: 2 mots) sans explosion
#: combinatoire ni faux positifs sur les phrases nominales.
_MAX_COMPOSITE_WORDS = 3


def _detect_composite_patronymes(
    tokens: list[tuple[int, int, str]],
    cfold_tokens: list[str],
    noms,
    trig_starts: list[int],
    trig_max_te: list[int],
    window: int,
) -> list[Span]:
    """Phase 35 — D35e: patronymes composés (2-3 mots) du gazetteer noms.

    Une entrée multi-mots du gazetteer (ex. « ALTOUBAH MIANGOGO ») dont chaque
    token seul est absent du gazetteer n'était pas masquée (fuite S1): aucun
    span simple n'était émis, ``GazetteerCipher.encrypt`` renvoyait ``None`` et
    le texte ressortait inchangé. Ce détecteur émet un span composé UNIQUE
    couvrant les mots (l'entrée composée EST dans le gazetteer, donc masquable
    par le cipher). Modèle: ``places._phrase_matches`` (plus longue phrase,
    prefiltre ``multi_word_first_words``).

    Confiance: ``_BOOSTED`` si un déclencheur est proche, ``_BASE`` sinon. Les
    composés nus restent filtrés par le candidat nu en permissive (phase 34,
    D34b: pas de régression). Renvoie la liste brute (l'arbitrage des
    chevauchements avec les spans simples est du ressort de ``resolve_overlaps``).
    """
    spans: list[Span] = []
    i = 0
    while i < len(tokens):
        # Un premier token chevauchant un déclencheur (ex. « M » dans « M. »)
        # est la partie lettrée du déclencheur, pas le début d'un patronyme
        # composé. Sans ce garde, l'abréviation « M. » deviendrait le premier
        # token d'entrées réelles du gazette commençant par « M » (ex. « M
        # AATALLA ») et le déclencheur serait absorbé dans le span composé.
        if _overlaps_trigger(tokens[i][0], tokens[i][1], trig_starts, trig_max_te):
            i += 1
            continue
        first_key = cfold_tokens[i]
        if first_key in noms.multi_word_first_words and i + 1 < len(tokens):
            best: tuple[int, int, str] | None = None
            cfold_words: list[str] = []
            words: list[str] = []
            for k in range(i, min(i + _MAX_COMPOSITE_WORDS, len(tokens))):
                words.append(tokens[k][2])
                cfold_words.append(cfold_tokens[k])
                # k > i: un composé couvre AU MOINS 2 tokens. Sans ce garde-fou,
                # un premier mot seul dans le gazette (ex. « M », initiale dans
                # load_noms) serait émis comme composé et substitué.
                if k > i and " ".join(cfold_words) in noms:
                    best = (tokens[i][0], tokens[k][1], " ".join(words))
            if best is not None:
                start, end, value = best
                near = _near_trigger(start, end, trig_starts, trig_max_te, window)
                spans.append(
                    Span(
                        start=start,
                        end=end,
                        type=EntityType.PATRONYME,
                        value=value,
                        rule_id="gazetteer-nom",
                        confidence=_BOOSTED if near else _BASE,
                    )
                )
                # Ne pas re-matcher les tokens couverts par le composé.
                i = _token_index_after(tokens, end)
                continue
        i += 1
    return spans


def _token_index_after(tokens: list[tuple[int, int, str]], pos: int) -> int:
    """Indice du premier token dont le début est >= ``pos`` (recherche linéaire)."""
    for idx, (s, _e, _v) in enumerate(tokens):
        if s >= pos:
            return idx
    return len(tokens)


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

    tokens: list[tuple[int, int, str]] = [
        (m.start(), m.end(), m.group(0)) for m in _TOKEN_RE.finditer(text)
    ]
    cfold_tokens = [v.casefold() for (_, _, v) in tokens]

    spans: list[Span] = []
    for tok_start, tok_end, value in tokens:
        key = value.casefold()
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
        # Phase 34 — R1 (D34a, OBJ-010): EXCLUDED_NOMS est un filtre global
        # PATRONYME. Un token dont le casefold est dans la liste n'est JAMAIS
        # émis comme PATRONYME, quel que soit le chemin (gazetteer-nom ou
        # context-capture). La liste reste scopée PATRONYME (les PRENOM ne
        # sont pas concernés).
        if key in noms and key not in EXCLUDED_NOMS:
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
        if key not in prenoms and key not in noms and near and key not in EXCLUDED_NOMS:
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

    # Phase 35 — D35e: patronymes composés (2-3 mots) du gazetteer noms. Les
    # spans simples ci-dessus couvrent les tokens individuels; le span composé
    # (plus long, même confiance) gagne l'arbitrage ``resolve_overlaps`` et est
    # masqué en bloc par le cipher (l'entrée composée est dans le gazetteer).
    spans.extend(
        _detect_composite_patronymes(tokens, cfold_tokens, noms, trig_starts, trig_max_te, window)
    )
    return spans
