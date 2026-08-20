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

from anonyfy.types import EntityType, Span

__all__ = ["DEFAULT_PRIORITY", "resolve_overlaps"]

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

    def sort_key(s: Span) -> tuple[float, int, int]:
        # Tri décroissant: confiance (spécificité), longueur, priorité déclarée.
        return (s.confidence, s.end - s.start, prio.get(s.type, 0))

    ordered = sorted(spans, key=sort_key, reverse=True)

    selected: list[Span] = []
    for span in ordered:
        if not any(_overlaps(span, kept) for kept in selected):
            selected.append(span)

    selected.sort(key=lambda s: s.start)
    return selected
