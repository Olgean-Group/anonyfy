"""Gazetteers embarques figes (phase 09).

Chargeur paresseux des gazetteers INSEE/COG/BAN (prenoms, patronymes, communes,
voies) avec empreinte de version figee. Voir ``loader`` pour l'API publique.

Reference: PLAN.md phase 09, ADR 0001 section 11.
"""

from anonyfy.detect.gazetteers.loader import (
    Gazetteer,
    GazetteerEntry,
    GazetteerVersionMismatch,
    check_gazetteer_version,
    gazetteer_version,
    load_communes,
    load_noms,
    load_prenoms,
    load_voies,
    reset_cache,
)

__all__ = [
    "Gazetteer",
    "GazetteerEntry",
    "GazetteerVersionMismatch",
    "check_gazetteer_version",
    "gazetteer_version",
    "load_communes",
    "load_noms",
    "load_prenoms",
    "load_voies",
    "reset_cache",
]
