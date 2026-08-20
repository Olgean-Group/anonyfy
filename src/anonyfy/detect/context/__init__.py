"""Sous-paquet context: déclencheurs contextuels et détection de candidats
noms/prénoms (phase 12).

Couplage avec la détection gazetteer (phase 09): un candidat « nom » sans
déclencheur à proximité a une confiance faible; un candidat avec déclencheur
dans une fenêtre de N caractères a une confiance élevée. Les déclencheurs
captent également un nom absent des listes (token capitalisé inconnu mais
proche d'un déclencheur).

Référence: PLAN.md phase 12, PRD §7 (plafond de confiance). Décision D20.
"""

from __future__ import annotations

__all__ = ["triggers"]
