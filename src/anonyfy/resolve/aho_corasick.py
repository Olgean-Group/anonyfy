"""Automate Aho-Corasick sur les substituts émis (phase 10b).

Construit un automate Aho-Corasick sur l'ensemble des **substituts** (surrogates)
émis dans un scope, indexé par substitut et par variantes normalisées prédites du
substitut (``variants.py``). Permet à ``unmask`` (phase 08) de retrouver les
substituts dans la réponse d'un modèle même reformatée (espaces, ponctuation,
casses, groupes de chiffres, « M. <nom> »).

**Invariant 1 (architecture §6)**: l'automate cherche **TOUJOURS les
SUBSTITUTS** dans le texte, jamais le clair. Les variantes s'appliquent au
substitut, pas au clair. Le registre n'expose jamais le clair (``lookup`` renvoie
un enregistrement index/HMAC, pas la valeur claire).

Deux points de construction:
- ``AhoCorasick.from_surrogates([...])``: depuis une liste explicite (tests en
  isolation, sans dépendre du registre).
- ``AhoCorasick.from_registry(r)``: depuis un registre ``ScopeRegistry`` (phase
  10), en énumérant les substituts émis via ``iter_surrogates()``.

L'automate est construit à la demande (lazy) à partir des substituts; il peut
être reconstruit si le registre grossit (invalidation par compte d'entrées).

Implémentation sans dépendance externe (Aho-Corasick classique: goto + failure +
output, BFS pour les liens de failure).

Référence: PLAN.md phase 10b, D7/OBJ-005, architecture §6, invariant 1.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from anonyfy.resolve import variants

if TYPE_CHECKING:
    from anonyfy.surrogate.registry import ScopeRegistry

__all__ = ["AhoCorasick", "Hit"]


@dataclass(frozen=True, slots=True)
class Hit:
    """Occurrence d'un substitut trouvée dans le texte.

    Attributes:
        substitute: le substitut canonique (surrogate) retrouvé.
        start: indice de début (inclusif) du match dans le texte.
        end: indice de fin (exclusif) du match dans le texte.
        match: la portion de texte effectivement matchée (variante ou substitut).
    """

    substitute: str
    start: int
    end: int
    match: str


class _Node:
    """Nœud du trie Aho-Corasick (goto/failure/output)."""

    __slots__ = ("children", "fail", "outputs", "depth")

    def __init__(self, depth: int) -> None:
        self.children: dict[str, _Node] = {}
        self.fail: _Node | None = None
        self.outputs: list[str] = []  # substituts matchés en ce nœud (terminal)
        self.depth: int = depth


class AhoCorasick:
    """Automate Aho-Corasick indexé par substituts et leurs variantes.

    L'automate cherche les **substituts** (et leurs variantes) dans le texte,
    jamais le clair (invariant 1).
    """

    def __init__(self) -> None:
        self._root: _Node = _Node(depth=0)
        self._built: bool = False

    # --- Construction -------------------------------------------------------

    def _add_pattern(self, pattern: str, substitute: str) -> None:
        """Insère un motif (variante ou substitut) associé à son substitut."""
        node = self._root
        for ch in pattern:
            child = node.children.get(ch)
            if child is None:
                child = _Node(depth=node.depth + 1)
                node.children[ch] = child
            node = child
        if substitute not in node.outputs:
            node.outputs.append(substitute)

    def _build_failure_links(self) -> None:
        """Calcule les liens de failure et propage les outputs (BFS)."""
        root = self._root
        root.fail = root
        queue: deque[_Node] = deque()
        for child in root.children.values():
            child.fail = root
            queue.append(child)
        while queue:
            node = queue.popleft()
            for ch, child in node.children.items():
                f = node.fail
                while f is not root and ch not in f.children:
                    f = f.fail  # type: ignore[assignment]
                candidate = f.children.get(ch)
                if candidate is not None and candidate is not child:
                    child.fail = candidate
                else:
                    child.fail = root
                # Propagation des outputs du lien de failure (suffix links).
                child.outputs.extend(child.fail.outputs)
                queue.append(child)
        self._built = True

    # --- API de construction publique ---------------------------------------

    @classmethod
    def from_surrogates(cls, surrogates: Iterable[str]) -> AhoCorasick:
        """Construit l'automate depuis une liste explicite de substituts.

        Pour les tests en isolation: ne dépend pas du registre. Chaque substitut
        est indexé avec ses variantes normalisées (``variants.expand``).
        """
        ac = cls()
        for sub in surrogates:
            if not sub:
                continue
            for variant in variants.expand(sub):
                ac._add_pattern(variant, sub)
        ac._build_failure_links()
        return ac

    @classmethod
    def from_registry(cls, registry: ScopeRegistry) -> AhoCorasick:
        """Construit l'automate depuis un registre ``ScopeRegistry`` (phase 10).

        Énumère les substituts émis via ``iter_surrogates()`` (le registre
        n'expose jamais le clair) et indexe chaque substitut avec ses variantes.
        """
        return cls.from_surrogates(registry.iter_surrogates())

    # --- Recherche ----------------------------------------------------------

    def find(self, text: str) -> list[Hit]:
        """Renvoie toutes les occurrences de substituts (et variantes) dans le texte.

        Chaque hit expose le substitut canonique retrouvé (``.substitute``) et
        la position du match. L'automate cherche les substituts, jamais le clair.
        """
        if not self._built:
            # from_surrogates/from_registry construisent toujours; garde-fou.
            self._build_failure_links()
        root = self._root
        node = root
        hits: list[Hit] = []
        for i, ch in enumerate(text):
            while node is not root and ch not in node.children:
                node = node.fail  # type: ignore[assignment]
            child = node.children.get(ch)
            if child is not None:
                node = child
            # else: node est root et ch absent -> on reste à root (self-loop)
            for sub in node.outputs:
                start = i - node.depth + 1
                hits.append(Hit(substitute=sub, start=start, end=i + 1, match=text[start : i + 1]))
        return hits
