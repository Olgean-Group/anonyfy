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
) -> list[Span]:
    """Résout les chevauchements: spécificité > longueur > priorité déclarée.

    Renvoie les spans non chevauchants, triés par position de début. Un span
    perdant est entièrement exclu (pas de tronquage: l'identifiant perdant n'est
    pas un préfixe valide du gagnant dans tous les cas).
    """
    if not spans:
        return []

    prio = priority if priority is not None else DEFAULT_PRIORITY

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
