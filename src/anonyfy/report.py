"""Rapport d'activité lisible par un non-développeur (phase 15).

``render_report()`` produit une synthèse au format Markdown (lisible dans un
éditeur ou GitHub, structure stable pour diff): types rencontrés, volumes,
règles actives, version des gazetteers (PRD F10). Aucune valeur claire ni
substitut n'apparaît (invariant 1).

Le rapport reflète l'état du Vault (compteurs mis à jour à chaque ``mask``).
Pas de timestamp: le rapport est une synthèse de l'état, pas un journal
horodaté (rôle de l'AuditLog phase 14).
"""

from __future__ import annotations

from collections import Counter

from anonyfy.detect.gazetteers.loader import gazetteer_version
from anonyfy.types import EntityType

__all__ = ["render_report"]


# Libellés français lisibles par un non-développeur.
_TYPE_LABELS: dict[EntityType, str] = {
    EntityType.NIR: "NIR",
    EntityType.SIREN: "SIREN",
    EntityType.SIRET: "SIRET",
    EntityType.IBAN: "IBAN",
    EntityType.TVA: "TVA",
    EntityType.CARTE_BANCAIRE: "carte bancaire",
    EntityType.TELEPHONE: "téléphone",
    EntityType.PLAQUE_SIV: "plaque SIV",
    EntityType.REFERENCE_DOSSIER: "référence de dossier",
    EntityType.EMAIL: "email",
    EntityType.DATE: "date",
    EntityType.PATRONYME: "nom (patronyme)",
    EntityType.PRENOM: "prénom",
    EntityType.COMMUNE: "commune",
    EntityType.VOIE: "voie",
}


def render_report(
    *,
    type_counts: Counter,
    rule_ids: set[str],
    mask_calls: int,
) -> str:
    """Produit le rapport Markdown pour l'état donné.

    Args:
        type_counts: compte de spans par EntityType rencontrés lors des masquages.
        rule_ids: ensemble des identifiants de règles déclenchés.
        mask_calls: nombre d'appels ``mask`` effectués.

    Retourne une chaîne Markdown stable (déterministe: pas de timestamp, tri
    déterministe des types et règles). Ne contient jamais de clair ni de
    substitut (invariant 1).
    """
    total_spans = sum(type_counts.values())
    lines: list[str] = []
    lines.append("# Rapport d'activité anonyfy")
    lines.append("")
    lines.append("## Volumes")
    lines.append(f"- Appels mask: {mask_calls}")
    lines.append(f"- Total spans: {total_spans}")
    lines.append("")
    lines.append("## Types rencontrés")
    if type_counts:
        lines.append("| Type | Occurrences |")
        lines.append("|------|-------------|")
        for etype in sorted(type_counts, key=lambda t: t.value):
            label = _TYPE_LABELS.get(etype, etype.value)
            lines.append(f"| {label} | {type_counts[etype]} |")
    else:
        lines.append("Aucun type rencontré.")
    lines.append("")
    lines.append("## Règles actives")
    if rule_ids:
        for rid in sorted(rule_ids):
            lines.append(f"- {rid}")
    else:
        lines.append("Aucune règle déclenchée.")
    lines.append("")
    lines.append("## Versions des gazetteers")
    lines.append(f"- gazetteer_version: {gazetteer_version()}")
    lines.append("")
    return "\n".join(lines)
