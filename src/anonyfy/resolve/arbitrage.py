"""Arbitrage des chevauchements d'identifiants structurés (phase 08, PRD F2).

Résout les chevauchements entre spans détectés par priorité:
  1. spécificité (confidence: 1.0 pour clé arithmétique, 0.9 pour format seul);
  2. longueur du span (plus long = plus spécifique, ex. SIRET 14 > SIREN 9);
  3. priorité déclarée par type (ex. SIRET > CB pour un même nombre de 14 chiffres).

L'algorithme trie les spans par (spécificité décroissante, longueur décroissante,
priorité déclarée décroissante) puis sélectionne gloutonnement les spans qui ne
chevauchent pas un span déjà sélectionné. Les spans résolus sont renvoyés triés
par position de début.

Périmètre phase 08: types structurés uniquement (D2: NIR, SIREN, SIRET, IBAN, TVA,
CB, téléphone). Les chevauchements non structurés (patronyme, plaque, etc.) sont
traités en phase 13.

Référence: PLAN.md phase 08, PRD F2, architecture §4.
"""

from __future__ import annotations

import bisect

from anonyfy.detect.context import places
from anonyfy.types import EntityType, Span

__all__ = ["DEFAULT_PRIORITY", "resolve_overlaps"]

# Phase 28 — S3: un patronyme confirmé par déclencheur contextuel (« M. », « Mme »…)
# prime sur un span COMMUNE ou VOIE chevauchant de même longueur (interdiction du
# repli communes/voies sur les patronymes, PRD F3 « substitut de même type »). Un
# token typé PATRONYME par déclencheur ne doit jamais être substitué par une
# commune ou une voie, même s'il figure aussi dans ces gazetteers (ex. BOISSEAU
# = patronyme + commune ; CHAMPAGNE = patronyme + commune + voie).
#
# Seul ``gazetteer-nom`` (patronyme présent dans le gazetteer noms, donc
# chiffrable par permutation d'index) est admis. ``context-capture`` (token
# inconnu capté par déclencheur) est exclu: si un tel token est aussi une
# commune, c'est une commune légitime et le cipher patronyme ne pourrait de
# toute façon pas le chiffrer (token absent du gazetteer noms), laissant le
# span en clair (fuite). La commune, qui peut le chiffrer, doit donc gagner.
_CAPTURE_RULES: frozenset[str] = frozenset({"gazetteer-nom"})
_CAPTURE_MIN_CONFIDENCE: float = 0.8


def _is_captured_patronyme(span: Span) -> bool:
    """True si le span est un PATRONYME confirmé par déclencheur contextuel.

    Règle admise: ``gazetteer-nom`` à confiance élevée (boosté par déclencheur,
    0.9). ``context-capture`` (token inconnu, 0.8) est exclu car le cipher
    patronyme ne peut pas chiffrer un token absent du gazetteer noms. Sans
    déclencheur (``gazetteer-nom`` à 0.5), le patronyme n'est pas « capté » et le
    comportement par défaut (COMMUNE prioritaire) est préservé.
    """
    return (
        span.type == EntityType.PATRONYME
        and span.rule_id in _CAPTURE_RULES
        and span.confidence >= _CAPTURE_MIN_CONFIDENCE
    )


def _is_apres_verbe_adresse(span: Span, text: str) -> bool:
    """True si le span suit immédiatement un verbe d'adresse (D42c).

    Phase 50 — REV-MAJ-1: le déclencheur patronyme ``demeurant`` (phase 12,
    fenêtre 40) booste à tort un token d'adresse situé après lui
    (« demeurant à Paris » -> ``Paris`` boosté PATRONYME 0.9) alors que le
    token est une COMMUNE en contexte d'adresse. Le TITRE (« M. Paris ») reste
    un déclencheur patronyme légitime : seul un verbe d'adresse complet
    (``places.ADDRESS_VERBS``, source unique REV-MIN-4) neutralise le boost.
    """
    return places._trigger_before(
        span.start, text, places.ADDRESS_VERBS, places.ADDRESS_VERB_WINDOW
    )


# Priorité déclarée par type (plus élevé = gagne les égalités).
# SIRET (14 chiffres, structure SIREN+NIC) est plus spécifique que CB (13-19
# chiffres) pour un même nombre de 14 chiffres Luhn-valide.
# Types gazetteer (phase 13): une voie est plus spécifique qu'une commune (elle
# contient souvent le type de voie + le toponyme), elle-même plus spécifique
# qu'un patronyme isolé, lui-même plus spécifique qu'un prénom (souvent court
# et ambigu). Tranche les égalités (même confiance, même longueur) entre
# candidats gazetteer chevauchants.
DEFAULT_PRIORITY: dict[EntityType, int] = {
    EntityType.SIRET: 6,
    EntityType.NIR: 5,
    EntityType.IBAN: 5,
    EntityType.TVA: 5,
    EntityType.CARTE_BANCAIRE: 4,
    EntityType.SIREN: 3,
    EntityType.TELEPHONE: 2,
    EntityType.VOIE: 4,
    EntityType.COMMUNE: 3,
    EntityType.PATRONYME: 2,
    EntityType.PRENOM: 1,
    EntityType.PLAQUE_SIV: 1,
    EntityType.REFERENCE_DOSSIER: 1,
    EntityType.EMAIL: 1,
    EntityType.DATE: 1,
}


def _overlaps(a: Span, b: Span) -> bool:
    """Deux spans se chevauchent-ils (intervalles semi-ouverts)?"""
    return a.start < b.end and b.start < a.end


def resolve_overlaps(
    spans: list[Span],
    *,
    priority: dict[EntityType, int] | None = None,
    text: str | None = None,
) -> list[Span]:
    """Résout les chevauchements: spécificité > longueur > priorité déclarée.

    Renvoie les spans non chevauchants, triés par position de début. Un span
    perdant est entièrement exclu (pas de tronquage: l'identifiant perdant n'est
    pas un préfixe valide du gagnant dans tous les cas).

    ``text`` (optionnel) active la neutralisation REV-MAJ-1 : un PATRONYME boosté
    par le déclencheur ``demeurant`` mais situé après un verbe d'adresse et
    chevauchant une COMMUNE/VOIE est retiré, pour que la lecture d'adresse gagne
    (F3-type). Sans ``text``, l'arbitrage est inchangé (appels hors moteur).
    """
    if not spans:
        return []

    prio = priority if priority is not None else DEFAULT_PRIORITY

    # Phase 50 — REV-MAJ-1: « demeurant à Paris » émettait PATRONYME (boost du
    # déclencheur ``demeurant``, phase 12) et l'étape S3 ci-dessous retirait la
    # COMMUNE chevauchante : un token d'adresse ambigui (patronyme + commune)
    # était typé PATRONYME, violant F3-type. Un PATRONYME immédiatement précédé
    # d'un verbe d'adresse et chevauchant une COMMUNE/VOIE est le nom de
    # l'adresse, pas une personne : on retire la lecture patronyme, la
    # commune/voie reste (le clair est toujours masqué, invariant 1).
    # Borné : sans verbe d'adresse (« M. Paris ») le boost patronyme est
    # conservé ; sans COMMUNE/VOIE concurrente, le span n'est pas touché.
    if text is not None:
        lieux = [
            s
            for s in spans
            if s.type in (EntityType.COMMUNE, EntityType.VOIE) and _is_apres_verbe_adresse(s, text)
        ]
        if lieux:
            spans = [
                s
                for s in spans
                if not (
                    s.type == EntityType.PATRONYME
                    and _is_apres_verbe_adresse(s, text)
                    and any(_overlaps(s, lieu) for lieu in lieux)
                )
            ]
            if not spans:
                return []

    # Phase 39 — R4 (D39a/D39b): un token PRENOM+COMMUNE adjacent à un candidat
    # PATRONYME (ou PRENOM) est une PERSONNE, pas une commune : la lecture
    # « commune » n'est presque jamais adjacente à un nom de personne
    # (« Marie Lefebvre » = Marie PRENOM + Lefebvre PATRONYME, F3 conservé).
    # Mécanisme : retirer les spans COMMUNE et le span de type opposé du token
    # PRENOM ambigu, pour que la sélection gloutonne type correctement :
    #  - candidat adjacent À DROITE (s.start == p.end + 1) : le token est le
    #    PREMIER nom (« Marie Lefebvre ») -> le PATRONYME du token est retiré,
    #    le PRENOM gagne ;
    #  - candidat adjacent À GAUCHE (p.start == s.end + 1) : le token est le
    #    DERNIER nom (« Pierre Bernard », Bernard -> PRENOM est le PRENOM du
    #    token, retiré) -> le PATRONYME du token gagne.
    # Sans candidat adjacent (D39d/D39e), aucun retrait : une commune ambiguë
    # (« à Paris », « à Marie ») reste COMMUNE (non-régression S4).
    # Placé AVANT le pré-filtre S3 : S3 retire la COMMUNE chevauchant un
    # PATRONYME capté, ce qui masquerait l'ambiguïté PRENOM+COMMUNE.
    personne = (EntityType.PATRONYME, EntityType.PRENOM)
    # Index du voisinage : spans de personne par position de début/fin, et
    # union disjointe des intervalles COMMUNE (arbre plat + bisect, comme le
    # glouton). Évite un rescan O(n) par span PRENOM (perf du texte dense,
    # phase 32 : 10 000 caractères, ~250 identifiants).
    par_debut: dict[int, list[Span]] = {}
    par_fin: dict[int, list[Span]] = {}
    communes: list[Span] = []
    for s in spans:
        if s.type in personne:
            par_debut.setdefault(s.start, []).append(s)
            par_fin.setdefault(s.end, []).append(s)
        elif s.type == EntityType.COMMUNE:
            communes.append(s)
    communes.sort(key=lambda s: s.start)
    union_communes: list[tuple[int, int]] = []
    for c in communes:
        if not union_communes or c.start > union_communes[-1][1]:
            union_communes.append((c.start, c.end))
        else:
            union_communes[-1] = (union_communes[-1][0], max(union_communes[-1][1], c.end))
    _starts_communes = [u[0] for u in union_communes]

    # Prénoms « ambigus » : un span PRENOM couvert par une commune ET adjacent
    # à un candidat PATRONYME/PRENOM. Rôle :
    #  - premier nom (« Marie Lefebvre ») : la COMMUNE et le PATRONYME du token
    #    sont retirés, le PRENOM gagne ;
    #  - dernier nom (« Pierre Bernard », Bernard) : la COMMUNE est retirée, le
    #    PATRONYME (confiance ou priorité 2) gagne déjà sur le PRENOM.
    prenoms_premiers: list[Span] = []
    prenoms_derniers: list[Span] = []
    for p in spans:
        if p.type != EntityType.PRENOM:
            continue
        j = bisect.bisect_right(_starts_communes, p.start)
        couvert = (j > 0 and union_communes[j - 1][1] > p.start) or (
            j < len(union_communes) and union_communes[j][0] < p.end
        )
        if not couvert:
            continue
        droite = par_debut.get(p.end + 1, ())
        gauche = par_fin.get(p.start - 1, ())
        if droite and not gauche:
            prenoms_premiers.append(p)
        elif gauche and not droite:
            prenoms_derniers.append(p)
        # gauche ET droite : token entre deux personnes (rare, ex. « Jean Marie
        # Lefebvre ») : pas de retrait, le comportement par défaut est conservé.
    if prenoms_premiers or prenoms_derniers:

        def _retire_d39(s: Span) -> bool:
            if s.type == EntityType.COMMUNE:
                return any(_overlaps(s, p) for p in prenoms_premiers) or any(
                    _overlaps(s, p) for p in prenoms_derniers
                )
            if s.type == EntityType.PATRONYME:
                return any(_overlaps(s, p) for p in prenoms_premiers)
            return False

        spans = [s for s in spans if not _retire_d39(s)]

    # Phase 28 — S3: retirer les spans COMMUNE/VOIE chevauchant un patronyme
    # capté par déclencheur contextuel, à condition que la commune/voie ne soit
    # pas strictement plus longue (une voie légitime comme « rue de BOISSEAU »
    # contient le patronyme mais s'étend au-delà: elle doit être conservée). Le
    # patronyme prime sur la commune/voie en présence de contexte (PRD F3); sans
    # cette étape, COMMUNE (priorité 3) ou VOIE (priorité 4) gagnerait le
    # tie-break contre PATRONYME (priorité 2) à confidence et longueur égales.
    captured = [s for s in spans if _is_captured_patronyme(s)]
    if captured:
        spans = [
            s
            for s in spans
            if not (
                s.type in (EntityType.COMMUNE, EntityType.VOIE)
                and any(
                    _overlaps(s, p) and (s.end - s.start) <= (p.end - p.start) for p in captured
                )
            )
        ]

    # Phase 38 — R3 (correctif R3, arbitré par l'orchestrateur): un span
    # PRENOM/PATRONYME entièrement contenu dans un span VOIE est une PARTIE DU
    # NOM DE LA VOIE (« rue Victor Hugo », « boulevard Jean Jaurès »), pas une
    # personne : la VOIE gagne. Sans voie couvrante (« M. Victor Hugo »), le
    # couple prénom+nom reste détecté (personne légitime, D38a).
    voies = [s for s in spans if s.type == EntityType.VOIE]
    if voies:
        personne_en_voie = [
            s
            for s in spans
            if s.type in (EntityType.PRENOM, EntityType.PATRONYME)
            and any(v.start <= s.start and s.end <= v.end for v in voies)
        ]
        if personne_en_voie:
            rejetes = {id(s) for s in personne_en_voie}
            spans = [s for s in spans if id(s) not in rejetes]

    def sort_key(s: Span) -> tuple[float, int, int]:
        # Tri décroissant: confiance (spécificité), longueur, priorité déclarée.
        return (s.confidence, s.end - s.start, prio.get(s.type, 0))

    ordered = sorted(spans, key=sort_key, reverse=True)

    # Sélection gloutonne O(n log n): on maintient les spans retenus triés par
    # position de début dans un interval tree plat (liste triée + bisect). Les
    # spans retenus ne se chevauchent jamais entre eux (invariant du glouton),
    # donc pour un nouveau span (s, e) il suffit de tester le voisin immédiat à
    # gauche (end > s) et l'absence de retained dont start ∈ [s, e) à droite.
    selected: list[Span] = []
    starts: list[int] = []
    for span in ordered:
        s, e = span.start, span.end
        j = bisect.bisect_right(starts, s)
        # Voisin de gauche: retained[j-1] (start <= s). Chevauchement si end > s.
        if j > 0 and selected[j - 1].end > s:
            continue
        # Voisin de droite: premier retained avec start >= e (pas de chevauchement).
        # S'il existe un retained avec start dans [s, e), il chevauche ce span.
        k = bisect.bisect_left(starts, e)
        if j < k:
            continue
        selected.insert(j, span)
        starts.insert(j, s)

    selected.sort(key=lambda s: s.start)
    return selected
