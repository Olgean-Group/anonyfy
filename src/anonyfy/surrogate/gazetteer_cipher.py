"""Cipher gazetteer par permutation keyée (D22, types non-FPE).

Patronyme/prenom/commune/voie: le clair est cherché dans le gazetteer (index
canonique trié), l'index est permuté via ``Permutation`` (Feistel + cycle-walking),
et le substitut est le nom du gazetteer à l'index permuté (nom plausible, ADR intent).

Nom inconnu du gazetteer -> ``None`` (non masqué, choix (ii) D22: on ne masque
que ce qu'on sait identifier + réverser; fuite résiduelle documentée, mode
observation phase 17 pour découvrir ces cas).

Réversibilité: pas de clair stocké. ``decrypt`` retrouve l'index clair via
``Permutation.decrypt`` puis lookup dans le gazetteer trié.
"""

from __future__ import annotations

from anonyfy.detect.gazetteers.loader import Gazetteer
from anonyfy.surrogate.permutation import Permutation


class GazetteerCipher:
    """Permutation keyée sur l'index canonique d'un gazetteer.

    Args:
        key: clé secrète.
        scope: identifiant de scope (déterminisme scopé).
        entity_type: type d'entité (patronyme/prenom/commune/voie).
        gazetteer: gazetteer embarqué (load_noms/load_prenoms/etc.).
    """

    def __init__(self, key: bytes, scope: str, entity_type: str, gazetteer: Gazetteer) -> None:
        # Liste ordonnée canonique: noms triés par casefold (stable, figé D5).
        self._names = sorted((e.name for e in gazetteer), key=str.casefold)
        self._pos = {name.casefold(): i for i, name in enumerate(self._names)}
        self._perm = Permutation(key=key, scope=scope, entity_type=entity_type, n=len(self._names))

    def encrypt(self, name: str) -> str | None:
        """Retourne un substitut plausible du gazetteer, ou None si nom inconnu."""
        cf = name.casefold()
        if cf not in self._pos:
            return None
        idx = self._pos[cf]
        sub_idx = self._perm.encrypt(idx)
        return self._names[sub_idx]

    def decrypt(self, substitute: str) -> str | None:
        """Retourne le nom clair, ou None si le substitut n'est pas du gazetteer."""
        cf = substitute.casefold()
        if cf not in self._pos:
            return None
        sub_idx = self._pos[cf]
        idx = self._perm.decrypt(sub_idx)
        return self._names[idx]


__all__ = ["GazetteerCipher"]