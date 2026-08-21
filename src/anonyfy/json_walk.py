"""Parcours récursif d'arbre JSON pour mask_json / unmask_json (phase 18).

Seules les feuilles ``str`` (valeurs chaîne) sont masquées/démasquées. Les clés
(dict keys), les valeurs structurelles (int/float/bool/null/list/dict) et les
chemins exemptés ne sont jamais touchés.

Limites documentées (hors périmètre phase 18, reportés en v2):
  - JSONPath avancé non supporté: pas de ``$..`` (descendant), pas de filtres
    ``[?()]``, pas de slicing ``[1:3]``, pas de wildcards de clé ``.*``.
  - Seuls les chemins simples ``$.a.b`` et ``$.tools[*].function.name`` sont
    reconnus. ``[*]`` est un wildcard d'index de liste uniquement.

Référence: PLAN.md phase 18, PRD §7 (jamais masquer ``function.name``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = ["walk_mask", "walk_unmask"]


def _compile_patterns(exempt: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    """Compile une liste de chemins simples en regex ancrées.

    ``$.tools[*].function.name`` -> ``^\\$\\.tools\\[\\d+\\]\\.function\\.name$``
    ``$.model`` -> ``^\\$\\.model$``

    ``[*]`` (wildcard d'index de liste) devient ``\\[\\d+\\]`` (crochets
    littéraux + un ou plusieurs chiffres). Tout le reste est échappé
    littéralement (regex standard).
    """
    compiled: list[re.Pattern[str]] = []
    for raw in exempt:
        if not raw:
            continue
        # re.escape puis remplacement du motif [*] échappé en \[\d+\].
        escaped = re.escape(raw)
        escaped = escaped.replace(re.escape("[*]"), r"\[\d+\]")
        compiled.append(re.compile(f"^{escaped}$"))
    return tuple(compiled)


def _is_exempt(path: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    """True si ``path`` matche au moins un motif exempt compilé."""
    return any(p.match(path) is not None for p in patterns)


def _join(path: str, key: str) -> str:
    """Concatène un segment de clé au chemin courant.

    ``$`` + ``model`` -> ``$.model``
    ``$.tools[0]`` + ``function`` -> ``$.tools[0].function``
    """
    return f"{path}.{key}" if path == "$" else f"{path}.{key}"


def walk_mask(
    node: object,
    mask_fn: object,
    exempt_patterns: tuple[re.Pattern[str], ...],
    path: str = "$",
) -> object:
    """Parcourt récursivement ``node`` et masque les feuilles ``str`` non
    exemptées via ``mask_fn(str) -> str``.

    Les clés (dict keys), int/float/bool/null, list et dict ne sont pas touchés.
    """
    if isinstance(node, str):
        if _is_exempt(path, exempt_patterns):
            return node
        return mask_fn(node)
    if isinstance(node, list):
        return [
            walk_mask(item, mask_fn, exempt_patterns, f"{path}[{i}]") for i, item in enumerate(node)
        ]
    if isinstance(node, dict):
        return {k: walk_mask(v, mask_fn, exempt_patterns, _join(path, k)) for k, v in node.items()}
    return node


def walk_unmask(
    node: object,
    unmask_fn: object,
    exempt_patterns: tuple[re.Pattern[str], ...],
    path: str = "$",
) -> object:
    """Parcourt récursivement ``node`` et démasque les feuilles ``str`` non
    exemptées via ``unmask_fn(str) -> str``.

    Les chemins exemptés ne sont pas démasqués (la valeur est laissée telle
    quelle, ce qui correspond à une valeur non masquée à l'origine).
    """
    if isinstance(node, str):
        if _is_exempt(path, exempt_patterns):
            return node
        return unmask_fn(node)
    if isinstance(node, list):
        return [
            walk_unmask(item, unmask_fn, exempt_patterns, f"{path}[{i}]")
            for i, item in enumerate(node)
        ]
    if isinstance(node, dict):
        return {
            k: walk_unmask(v, unmask_fn, exempt_patterns, _join(path, k)) for k, v in node.items()
        }
    return node
