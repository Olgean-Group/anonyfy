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
import dataclasses
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
        # Phase 45 — R5 (D45a) : participe passé « fait » (formule « Fait à
        # <commune> »). Présent dans le gazetteer noms, il était émis PATRONYME
        # en initiale de phrase ; c'est le participe passé le plus fréquent de
        # la langue, jamais un patronyme en contexte de formule (OBJ-109).
        "fait",
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
#
# Phase 55 — OE-LIGATURE-DETECT: « Œ » (U+0152) est hors de la plage `À-Ý`
# (U+00C0-U+00DD) et « œ » (U+0153) hors de `À-ÿ` (U+00C0-U+00FF) : sans les
# ligatures explicites, « Œuilly » était tronqué en « uilly » et le token ne
# matchait plus le gazetteer. Idem « æ »/« Æ » (dans `À-ÿ`, mais inclus par
# cohérence avec places._TOKEN_RE).
_LIGATURES = "\u0152\u0153\u00c6\u00e6\u0178\u00ff"  # Œ œ Æ æ Ÿ ÿ
_TOKEN_RE = re.compile(rf"[A-ZÀ-Ý{_LIGATURES}][A-Za-zÀ-ÿ{_LIGATURES}'’-]*")

#: Nombre maximum de tokens d'un patronyme composé (phase 35, D35e). Les
#: entrées multi-mots du gazetteer noms (220 200) vont jusqu'à ~8 mots; borné à
#: 3 pour la détection des composés courants (recette S1: 2 mots) sans explosion
#: combinatoire ni faux positifs sur les phrases nominales.
_MAX_COMPOSITE_WORDS = 3


def _has_letters_between(text: str, a: int, b: int) -> bool:
    """True si un caractère lettré se trouve entre les positions ``a`` et ``b``.

    « La rue Victor Hugo » : entre « La » (fin 2) et « Victor » (début 7) il y
    a « rue » -> True (mots non adjacents). Entre « Victor » et « Hugo » il
    n'y a qu'un espace -> False (adjacents). Utilisé par le détecteur de
    patronymes composés pour ne pas sauter par-dessus des mots non capitalisés
    (ex. « Le Fournier » détecté sur « Le rapport a été rédigé par Fournier »).
    """
    return any(ch.isalpha() for ch in text[a:b])


def _detect_composite_patronymes(
    tokens: list[tuple[int, int, str]],
    cfold_tokens: list[str],
    noms,
    trig_starts: list[int],
    trig_max_te: list[int],
    window: int,
    text: str,
    non_personne: set[int],
) -> list[Span]:
    """Phase 35 — D35e: patronymes composés (2-3 mots) du gazetteer noms.

    Une entrée multi-mots du gazetteer (ex. « ALTOUBAH MIANGOGO ») dont chaque
    token seul est absent du gazetteer n'était pas masquée (fuite S1): aucun
    span simple n'était émis, ``GazetteerCipher.encrypt`` renvoyait ``None`` et
    le texte ressortait inchangé. Ce détecteur émet un span composé UNIQUE
    couvrant les mots (l'entrée composée EST dans le gazetteer, donc masquable
    par le cipher). Modèle: ``places._phrase_matches`` (plus longue phrase,
    prefiltre ``multi_word_first_words``).

    Phase 38 — R3 (fix QA): deux gardes supplémentaires par rapport à D35e.
    (1) Adjacence texte : ``_TOKEN_RE`` ne garde que les mots capitalisés, donc
    « Le rapport a été rédigé par Fournier » tokenise « Le » et « Fournier »
    comme « adjacents » alors que le déterminant et le nom sont séparés par
    des mots non capitalisés. Sans garde, le composé réel « LE FOURNIER »
    (présent dans le gazetteer) est émis en un span couvrant TOUTE la phrase
    (« Le [rapport a été rédigé par] Fournier ») et avale le patronyme réel.
    (b) Garde non personne : un composé dont un token couvert porte un marqueur
    de contexte non personnel (« La rue Victor Hugo ») est le nom d'une voie,
    pas une personne (même règle que les spans simples, D38b/D38f).

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
                # Phase 38 — R3 (fix QA): garde non contexte (b) : un token
                # couvert par un marqueur non personne stoppe le composé.
                if k in non_personne:
                    break
                # Phase 38 — R3 (fix QA): adjacence (a) : si un mot non
                # capitalisé se trouve entre deux tokens, ils ne sont pas
                # adjacents et ne peuvent former un patronyme composé.
                if k > i and _has_letters_between(text, tokens[k - 1][1], tokens[k][0]):
                    break
                words.append(tokens[k][2])
                cfold_words.append(cfold_tokens[k])
                # k > i: un composé couvre AU MOINS 2 tokens. Sans ce garde-fou,
                # un premier mot seul dans le gazette (ex. « M », initialie
                # dans load_noms) serait émis comme composé et substitué.
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


#: Phase 38 — R3 (D38c): un candidat est en « position structurelle » si le
#: dernier mot avant lui est « et » (énumération « X, Y et Z »).
_STRUCT_ET_RE = re.compile(r"\bet\s*$", re.IGNORECASE)


def _in_structural_position(text: str, tok_start: int) -> bool:
    """True si le token à ``tok_start`` est dans une position structurelle.

    Phase 38 — R3 (D38c): après ``Présents :``, ``Cordialement,``, en cellule de
    tableau (label ``:``), dans une énumération (après ``,`` ou « et »), en début
    de ligne non-première (bloc de signature de courriel). Une position
    structurelle désigne une personne avec quasi-certitude, sans titre : le
    candidat y est émis (confiance élevée).
    """
    if tok_start <= 0:
        return False
    i = tok_start - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    if i >= 0 and text[i] in (":", ",", "|"):
        return True
    if text[tok_start - 1] == "\n":
        return True
    return bool(_STRUCT_ET_RE.search(text[:tok_start]))


#: Phase 38 — R3 (correctif R3, arbitré par l'orchestrateur): marqueurs de
#: contexte NON PERSONNEL. Un candidat PRENOM/PATRONYME dont le début de phrase
#: porte un mot d'organisation (« société », « cabinet », « groupe »...) ou de
#: toponymisation (« rue », « boulevard », « quai »...) est le NOM D'UNE SOCIÉTÉ
#: ou D'UNE VOIE, pas une personne : l'émettre ferait chuter la précision du
#: corpus négatif figé (D38f). Ce garde est la « vraie réponse position/voisinage »
#: évoquée au PLAN phase 38 (pas une refonte du système, pas de données réelles).
_NON_PERSONNE_MARKERS: frozenset[str] = frozenset(
    {
        # Organisations (nom de société/cabinet/groupe/entreprise).
        "société",
        "societe",
        "cabinet",
        "groupe",
        "entreprise",
        "association",
        "fondation",
        "bureau",
        "agence",
        "syndicat",
        "établissement",
        "etablissement",
        "administration",
        "clinique",
        "magasin",
        "usine",
        "mairie",
        "école",
        "ecole",
        # Voies et lieux (toponyme = pas une personne).
        "rue",
        "boulevard",
        "avenue",
        "quai",
        "place",
        "pont",
        "allée",
        "allee",
        "chemin",
        "impasse",
        "square",
        "esplanade",
        "cours",
        "route",
        "gare",
        "mont",
        "tour",
        "parc",
        "port",
        "village",
        "château",
        "chateau",
        "hameau",
        "clause",
        "église",
        "eglise",
        "cathédrale",
        "cathedrale",
        "basilique",
    }
)
_MARKER_LOOKBACK_WORDS: int = 5


def _non_personne_position(text: str, tok_start: int) -> bool:
    """True si la même phrase porte un marqueur non personnel juste avant le token.

    Fenêtre bornée (``_MARKER_LOOKBACK_WORDS`` mots en arrière, sans franchir
    une fin de phrase). Ex. : « La société Dupont », « La rue Victor Hugo » ->
    les candidats prénom/nom y sont le nom de la société/voie, pas une personne.
    « M. Dupont » (titre) et « Jean Dupont » (couple) ne portent aucun marqueur :
    le mécanisme ne s'y applique pas.
    """
    if tok_start <= 0:
        return False
    n = 0
    j = tok_start - 1
    while j >= 0 and n < _MARKER_LOOKBACK_WORDS:
        while j >= 0 and not text[j].isalpha():
            if text[j] in ".!?…\n»":
                return False
            j -= 1
        if j < 0:
            return False
        end = j + 1
        while j >= 0 and text[j].isalpha():
            j -= 1
        if text[j + 1 : end].casefold() in _NON_PERSONNE_MARKERS:
            return True
        n += 1
    return False


def _boost_couples(
    spans: list[Span],
    text: str,
    tokens: list[tuple[int, int, str]],
    cfold_tokens: list[str],
    prenoms,
    noms,
    non_personne: set[int],
) -> None:
    """Phase 38 — R3 (D38a): « deux tokens donnent un déclencheur ».

    Un PRENOM connu (gazetteer prénoms) immédiatement adjacent (seuls des
    espaces les séparent) à un PATRONYME connu (gazetteer noms) forme un couple
    « prénom+nom » : les deux candidats passent à ``_BOOSTED`` (>= 0.8), sans
    titre. Rattrape ``Jean Dupont``, ``Marie Lefebvre``, ``Claire Bernard``.

    Un mot grammatical du gazetteer prénoms (« Le », « La », « Il »...) n'est
    pas éligible au couple : ``EXCLUDED_NOMS`` (mot-outil, pas un prénom de
    personne) — sans ce garde, « Le Bernard » (groupe) deviendrait un couple.
    Idem pour les candidats en contexte non personnel (``non_personne``,
    correctif R3) : « La rue Victor Hugo » ne doit pas devenir un couple.
    """
    if len(tokens) < 2:
        return
    for i in range(len(tokens) - 1):
        if i in non_personne or i + 1 in non_personne:
            continue
        s0, e0 = tokens[i][0], tokens[i][1]
        s1, e1 = tokens[i + 1][0], tokens[i + 1][1]
        if not text[e0:s1].isspace():
            continue
        if (
            cfold_tokens[i] in EXCLUDED_NOMS
            or cfold_tokens[i + 1] in EXCLUDED_NOMS
            or cfold_tokens[i] not in prenoms
            or cfold_tokens[i + 1] not in noms
        ):
            continue
        for idx, sp in enumerate(spans):
            if sp.start == s0 and sp.end == e0 and sp.type == EntityType.PRENOM:
                spans[idx] = dataclasses.replace(sp, confidence=_BOOSTED)
            elif sp.start == s1 and sp.end == e1 and sp.type == EntityType.PATRONYME:
                spans[idx] = dataclasses.replace(sp, confidence=_BOOSTED)


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
    # Phase 38 — R3 (correctif R3): candidats en contexte non personnel
    # (organisation/lieu) : pas émis comme PRENOM/PATRONYME.
    non_personne = {
        idx
        for idx, (tok_start, _tok_end, _val) in enumerate(tokens)
        if _non_personne_position(text, tok_start)
    }
    for idx, (tok_start, tok_end, value) in enumerate(tokens):
        key = value.casefold()
        # Un token chevauchant un déclencheur (ex. « M » dans « M. ») est la
        # partie lettrée du déclencheur lui-même, pas un candidat nom.
        if _overlaps_trigger(tok_start, tok_end, trig_starts, trig_max_te):
            continue
        title_near = _near_trigger(tok_start, tok_end, trig_starts, trig_max_te, window)
        # Phase 38 — R3 (correctif R3): contexte non personnel (organisation /
        # lieu) : pas émis comme PRENOM/PATRONYME. Le garde ne s'applique que
        # SANS titre : « M. ABC AGENCE BUREAU CONSULTANT » est une personne
        # (le garde doit rester inerte sous un titre « M. »/« Mme »/« Maître »).
        if idx in non_personne and not title_near:
            continue
        # Phase 38 — R3 (D38c): une position structurelle (liste, cellule de
        # tableau, énumération, début de ligne de signature) vaut déclencheur.
        near = title_near or _in_structural_position(text, tok_start)

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

    # Phase 38 — R3 (D38a): couple prénom+nom adjacent = déclencheur. À faire
    # avant l'arbitrage (les spans boostés à >= 0.8 sortent du filtre candidat nu).
    _boost_couples(spans, text, tokens, cfold_tokens, prenoms, noms, non_personne)

    # Phase 35 — D35e: patronymes composés (2-3 mots) du gazetteer noms. Les
    # spans simples ci-dessus couvrent les tokens individuels; le span composé
    # (plus long, même confiance) est gagné par l'arbitrage ``resolve_overlaps``
    # et est masqué en bloc par le cipher (l'entrée composée est dans le gazetteer).
    spans.extend(
        _detect_composite_patronymes(
            tokens, cfold_tokens, noms, trig_starts, trig_max_te, window, text, non_personne
        )
    )
    return spans
