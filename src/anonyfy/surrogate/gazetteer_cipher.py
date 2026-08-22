"""Cipher gazetteer par permutation keyée (D22, types non-FPE).

Patronyme/prenom/commune/voie: le clair est cherché dans le gazetteer (index
canonique trié), l'index est permuté via ``Permutation`` (Feistel + cycle-walking),
et le substitut est le nom du gazetteer à l'index permuté (nom plausible, ADR intent).

Nom inconnu du gazetteer -> ``None`` (non masqué, choix (ii) D22: on ne masque
que ce qu'on sait identifier + réverser; fuite résiduelle documentée, mode
observation phase 17 pour découvrir ces cas).

Réversibilité: pas de clair stocké. ``decrypt`` retrouve l'index clair via
la table inverse puis lookup dans le gazetteer trié.

Phase 25 (OBJ-REC-110): sondage non-fixe à la construction. Une permutation
aléatoire a en moyenne un point fixe (perm(idx) == idx); sur un scope dense,
un ou deux noms sortiraient en clair. Le sondage parcourt la permutation
entière, identifie les points fixes et les élimine par rotation circulaire de
leurs images (bijection préservée). Le résultat est un dérangement (permutation
sans point fixe). Déterminisme préservé: même (scope, type, clair, clé) -> même
substitut non-fixe.

Risque: pour n=1, un dérangement est impossible (le seul élément est un point
fixe); le point fixe est conservé (cas dégénéré, non observé en pratique avec
les gazetteers réels). Pour n >= 2, un dérangement existe toujours.

Cache: le dérangement ne dépend que de (key, scope, entity_type, n), pas des
noms du gazetteer. Un cache de module évite le recalcul quand plusieurs
``Vault`` utilisent le même (key, scope).

Phase 27 (OBJ-REC-107): remplacement du dict ``_pos`` par tri + ``bisect``
(O(log n), zéro dict). Sur 879k noms, le dict ``_pos`` consommait ~220-320 Mo;
la liste triée ``_cf_names`` + bisect consomme ~30 Mo (les chaînes casefold
seulement, pas de table de hachage). Le lookup O(log n) reste négligeable
(~20 comparaisons sur 879k entrées).
"""

from __future__ import annotations

import bisect

from anonyfy.detect.gazetteers.loader import Gazetteer
from anonyfy.surrogate.permutation import Permutation

# Cache de module: (key, scope, entity_type, n) -> (forward, inverse).
# Le dérangement ne dépend que de la permutation (key/scope/type/n), pas des
# noms du gazetteer. Évite le recalcul quand plusieurs Vault utilisent le même
# (key, scope).
_DERANGEMENT_CACHE: dict[tuple[bytes, str, str, int], tuple[list[int], list[int]]] = {}


def _remove_fixed_points(table: list[int], n: int) -> None:
    """Élimine les points fixes de la table de permutation (en place).

    Phase 25, sondage non-fixe. Stratégie bijective:
    - >= 2 points fixes: rotation circulaire de leurs images. Chaque point
      fixe ``f`` reçoit l'image du point fixe suivant. Aucun nouveau point
      fixe (tous les points fixes sont distincts).
    - 1 point fixe (n >= 2): échange avec le voisin ``(f+1) mod n``, qui n'est
      pas un point fixe (bijection préservée, aucun nouveau point fixe).
    - 1 point fixe (n == 1): dérangement impossible, conservé (cas dégénéré).
    - 0 point fixe: déjà un dérangement, rien à faire.

    Bijection: la rotation et l'échange sont des transpositions de valeurs
    dans la table; l'ensemble des valeurs est inchangé, la bijectivité est
    préservée.
    """
    fixed = [i for i in range(n) if table[i] == i]
    if len(fixed) >= 2:
        # Rotation circulaire: fixed[k] -> fixed[(k+1) % len(fixed)].
        # Les images actuelles des points fixes sont eux-mêmes (table[f] == f).
        # Après rotation, chaque point fixe reçoit l'image du suivant.
        for k, f in enumerate(fixed):
            table[f] = fixed[(k + 1) % len(fixed)]
    elif len(fixed) == 1 and n >= 2:
        # Échange avec le voisin (non point fixe, car len(fixed) == 1).
        f = fixed[0]
        j = (f + 1) % n
        table[f], table[j] = table[j], table[f]
    # else: 0 fixe (déjà dérangement) ou n == 1 (impossible à déranger).


class GazetteerCipher:
    """Permutation keyée sur l'index canonique d'un gazetteer (dérangement).

    Args:
        key: clé secrète.
        scope: identifiant de scope (déterminisme scopé).
        entity_type: type d'entité (patronyme/prenom/commune/voie).
        gazetteer: gazetteer embarqué (load_noms/load_prenoms/etc.).
    """

    def __init__(self, key: bytes, scope: str, entity_type: str, gazetteer: Gazetteer) -> None:
        # Liste ordonnée canonique: noms triés par casefold (stable, figé D5).
        self._names = sorted((e.name for e in gazetteer), key=str.casefold)
        # Phase 27 OBJ-REC-107: remplace le dict _pos par une liste triée de
        # casefold + bisect (O(log n), zéro dict). Évite ~220-320 Mo de RAM
        # sur 879k noms (dict hash table) -> ~30 Mo (liste de chaînes seule).
        self._cf_names = [n.casefold() for n in self._names]
        n = len(self._names)

        # Dérangement (phase 25): permutation sans point fixe. Le dérangement
        # ne dépend que de (key, scope, entity_type, n); on le cache pour éviter
        # le recalcul quand plusieurs Vault partagent le même (key, scope).
        cache_key = (bytes(key), scope, entity_type, n)
        cached = _DERANGEMENT_CACHE.get(cache_key)
        if cached is None:
            perm = Permutation(key=key, scope=scope, entity_type=entity_type, n=n)
            forward = [perm.encrypt(i) for i in range(n)]
            _remove_fixed_points(forward, n)
            inverse = [0] * n
            for i, v in enumerate(forward):
                inverse[v] = i
            _DERANGEMENT_CACHE[cache_key] = (forward, inverse)
            cached = (forward, inverse)
        self._forward = cached[0]
        self._inverse = cached[1]

    def _index_of(self, cf: str) -> int:
        """Index de ``cf`` dans la liste triée via bisect (O(log n)), ou -1."""
        i = bisect.bisect_left(self._cf_names, cf)
        if i < len(self._cf_names) and self._cf_names[i] == cf:
            return i
        return -1

    def encrypt(self, name: str) -> str | None:
        """Retourne un substitut plausible du gazetteer, ou None si nom inconnu.

        Phase 25: le substitut est garanti différent du clair (dérangement,
        aucun point fixe) pour n >= 2.
        """
        idx = self._index_of(name.casefold())
        if idx < 0:
            return None
        return self._names[self._forward[idx]]

    def decrypt(self, substitute: str) -> str | None:
        """Retourne le nom clair, ou None si le substitut n'est pas du gazetteer."""
        sub_idx = self._index_of(substitute.casefold())
        if sub_idx < 0:
            return None
        return self._names[self._inverse[sub_idx]]


__all__ = ["GazetteerCipher"]
