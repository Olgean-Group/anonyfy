"""Schéma normatif du rapport d'observation ``anonyfy.report.v1`` (phase 48).

Le contrat est packagé dans le paquet (``src/anonyfy/schemas/``) pour que les
consommateurs (dont ``anonyfy-audit``) chargent la source normative au lieu
d'une copie locale. Le schéma est draft 2020-12, agrégats uniquement: aucune
valeur source, aucun nom de fichier, aucun excerpt, aucun clair ni substitut.

Référence: ``docs/superpowers/plans/01-anonyfy-public-report-contract.md``
(phase 48, Task 1).
"""

from __future__ import annotations

import json
from importlib.resources import files

__all__ = ["load_report_schema"]


def load_report_schema() -> dict[str, object]:
    """Charge le schéma JSON normatif ``anonyfy.report.v1``.

    Retourne le schéma désérialisé. L'appelant le valide ou l'utilise avec
    ``Draft202012Validator``.
    """
    resource = files(__package__).joinpath("anonyfy.report.v1.schema.json")
    return json.loads(resource.read_text(encoding="utf-8"))
