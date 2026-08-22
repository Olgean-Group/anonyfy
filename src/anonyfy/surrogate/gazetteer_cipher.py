"""Cipher gazetteer par permutation keyée (D22, types non-FPE).

Patronyme/prenom/commune/voie: le clair est cherché dans le gazetteer (index
canonique trié), l'index est permuté via ``Permutation`` (Feistel + cycle-walking),
et le substitut est le nom du gazetteer à l'index permuté (nom plausible, ADR intent).

Nom inconnu du gazetteer -> ``None`` (non masqué, choix (ii) D22: on ne masque
que ce qu'on sait identifier + réverser; fuite résiduelle documentée, mode
observation phase 17 pour découvrir ces cas).

Réversibilité: pas de clair stocké. ``decrypt`` retrouve l'index clair via la
table inverse puis lookup dans le gazetteer trié.

Phase 35 (R2, D35a/D35b): permutation paresseuse. La matérialisation
``forward = [perm.encrypt(i) for i in range(n)]`` (879k chiffrements au
premier mask, 17-52 s) est supprimée: ``encrypt(name)`` calcule
``names[perm.encrypt(idx)]`` à la demande (O(1) par nom). Le dérangement
(``_remove_fixed_points``) est supprimé: les points fixes (~1 par gazetteer)
réapparaissent et sont traités par le filet de sûreté global dans
``Engine.mask`` (D35f) — aucune entrée ne ressort identique sans signal.

``probe`` (D35i): exposé pour le filet. Pour un nom indexé, le probe k rend
le nom à l'index ``perm.encrypt((idx + k) % n)`` (déterministe, bijectif:
deux (clair, k) distincts donnent deux (substitut, k) distincts tant que la
colonne n'est pas saturée). Pour un nom non indexé, renvoie ``None`` (le filet
avertit, dernier recours D35h).

Phase 27 (OBJ-REC-107): tri + ``bisect`` (O(log n), zéro dict). Sur 879k noms,
le dict ``_pos`` consommait ~220-320 Mo; la liste triée ``_cf_names`` + bisect
consomme ~30 Mo. Lookup O(log n) ~20 comparaisons.
"""

from __future__ import annotations

import bisect

from anonyfy.detect.gazetteers.loader import Gazetteer
from anonyfy.surrogate.permutation import Permutation


class GazetteerCipher:
    """Permutation keyée paresseuse sur l'index canonique d'un gazetteer.

    Args:
        key: clé secrète.
        scope: identifiant de scope (déterminisme scopé).
        entity_type: type d'entité (patronyme/prenom/commune/voie).
        gazetteer: gazetteer embarqué (load_noms/load_prenoms/etc.).
    """

    def __init__(self, key: bytes, scope: str, entity_type: str, gazetteer: Gazetteer) -> None:
        # Liste ordonnée canonique: noms triés par casefold (stable, figé D5).
        self._names = sorted((e.name for e in gazetteer), key=str.casefold)
        self._cf_names = [n.casefold() for n in self._names]
        n = len(self._names)
        self._perm = Permutation(key=key, scope=scope, entity_type=entity_type, n=n)

    def _index_of(self, cf: str) -> int:
        """Index de ``cf`` dans la liste triée via bisect (O(log n)), ou -1."""
        i = bisect.bisect_left(self._cf_names, cf)
        if i < len(self._cf_names) and self._cf_names[i] == cf:
            return i
        return -1

    def encrypt(self, name: str) -> str | None:
        """Retourne un substitut plausible du gazetteer, ou None si nom inconnu.

        Phase 35: calcul paresseux ``names[perm.encrypt(idx)]`` (O(1) par nom,
        plus de matérialisation de la permutation entière). Le substitut peut
        être un point fixe (== clair, ~1 par gazetteer); le filet global
        (D35f) s'en charge dans ``Engine.mask``.
        """
        idx = self._index_of(name.casefold())
        if idx < 0:
            return None
        return self._names[self._perm.encrypt(idx)]

    def decrypt(self, substitute: str) -> str | None:
        """Retourne le nom clair, ou None si le substitut n'est pas du gazetteer.

        La permutation est bijective: ``encrypt`` et ``decrypt`` sont des
        inverses (pas besoin de table inverse matérialisée).
        """
        sub_idx = self._index_of(substitute.casefold())
        if sub_idx < 0:
            return None
        return self._names[self._perm.decrypt(sub_idx)]

    def probe(self, name: str, probe: int = 1) -> str | None:
        """Substitut du nom avec un décalage déterministe (D35i, filet D35f).

        Pour un nom indexé ``idx``, renvoie le nom à l'index
        ``perm.encrypt((idx + probe) % n)`` (distinct de ``encrypt(name)`` si
        ``probe != 0``). Pour un nom non indexé, renvoie ``None``. Le probe
        reste déterministe (même clair -> même substitut de probe, invariant 2)
        et injectif par (idx, probe) : un vrai sondage borné (max 1000, D35h)
        permet de sortir d'un point fixe sans casser la bijectivité scopée.
        """
        idx = self._index_of(name.casefold())
        if idx < 0:
            return None
        n = len(self._names)
        return self._names[self._perm.encrypt((idx + probe) % n)]


__all__ = ["GazetteerCipher"]
