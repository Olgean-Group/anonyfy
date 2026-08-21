"""Journal d'audit (phase 14).

Méta uniquement, jamais le texte clair OU substitué (D10, OBJ-022).
Empreinte HMAC-SHA-256(key, texte_clair) figé (D3/OBJ-011): keyée, pas SHA-256
nu (inversible par dictionnaire).

Format: JSON lines (une ligne par appel ``Vault.mask``), append-only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

__all__ = ["AuditLog"]


class AuditLog:
    """Journal d'audit append-only en JSON lines.

    Une ligne JSON par appel ``Vault.mask``: horodatage, scope, compte de spans
    par type, rule_ids déclenchées, empreinte HMAC-SHA-256(key, texte_clair).

    Aucune valeur claire ni substitut n'est jamais écrite (PRD F9, D10).
    """

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def record(
        self,
        *,
        key: bytes,
        text: str,
        scope: str,
        entities,
        weak_spans=None,
    ) -> None:
        """Écrit une ligne d'audit pour un appel ``mask(text)``.

        ``entities`` est un itérable de ``Span`` (les spans détectés/substituts
        dans le texte masqué). L'empreinte est calculée sur ``text`` (clair
        d'entrée, jamais persisté) avec ``key`` (HMAC-SHA-256).

        ``weak_spans`` (phase 17, optionnel) est une liste de dicts de méta pour
        les spans de confiance faible non confirmés par contexte (policy
        permissive). Chaque dict ne contient QUE des méta (``entity_type``,
        ``confidence``, ``rule_id``), JAMAIS la valeur du span ni le texte clair
        (invariant 1, D10). Utilisé pour journaliser un avertissement sans fuite.
        """
        digest = hmac.new(key, text.encode("utf-8"), hashlib.sha256).hexdigest()
        counts = Counter(span.type.value for span in entities)
        rule_ids = sorted({span.rule_id for span in entities})
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "scope": scope,
            "digest": digest,
            "span_count_by_type": dict(counts),
            "rule_ids": rule_ids,
        }
        if weak_spans is not None:
            entry["weak_spans"] = weak_spans
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
