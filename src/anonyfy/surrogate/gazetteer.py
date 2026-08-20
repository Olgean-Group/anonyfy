"""Sélection déterministe de substituts par gazetteer (phase 11).

Sélectionne un substitut (nom/prenom/commune/voie) dans un gazetteer par
``index = HMAC-SHA256(key, scope || type || value) mod N``, avec préservation des
attributs (genre pour les prénoms, département pour les communes) via filtrage
préalable du gazetteer avant tirage.

Frontière avec le registre (phase 10): ``pick`` est une fonction pure stateless
qui sélectionne LE NOM du substitut dans le gazetteer; ``ScopeRegistry.reserve``
(phase 10) alloue le slot/persistance (indice formaté, sondage, SQLite) et gère
l'injectivité scopé. Les deux partagent la formule HMAC d'indice (HMAC sur
``scope\\x00type\\x00clair``) mais ne dupliquent pas de logique: ``pick`` ne
persiste rien et ne gère pas les collisions scopées (les critères d'acceptation
de la phase 11 ne le requièrent pas; l'injectivité relevée est du ressort de la
phase 10/13 au moment du mask). Le filtrage par attribut réduit l'espace de
collision et préserve les attributs (PLAN ligne 551-553).

La valeur claire n'est jamais persistée par ``pick`` (invariant 1): la fonction
calcule uniquement un indice HMAC et renvoie une entrée du gazetteer.

Référence: PLAN.md phase 11, ADR 0001 section 11, architecture §5.3.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from anonyfy.detect.gazetteers.loader import Gazetteer

__all__ = ["PickResult", "pick"]


@dataclass(frozen=True, slots=True)
class PickResult:
    """Substitut sélectionné dans un gazetteer, attributs préservés.

    Attributes:
        name: nom du substitut (entrée du gazetteer).
        gender: genre préservé (M/F/MF pour les prénoms), mappé depuis
            ``GazetteerEntry.genre``. Chaîne vide si non pertinent.
        departement: code département préservé (pour les communes), mappé depuis
            ``GazetteerEntry.departement``. Chaîne vide si non pertinent.
    """

    name: str
    gender: str = ""
    departement: str = ""


def pick(
    entity_type: str,
    clear_value: str,
    *,
    scope: str,
    key: bytes,
    gazetteer: Gazetteer,
    gender: str | None = None,
    departement: str | None = None,
) -> PickResult:
    """Sélectionne un substitut déterministe scopé dans ``gazetteer``.

    L'indice est dérivé via ``HMAC-SHA256(key, scope || type || value) mod N`` où
    ``N`` est la taille du gazetteer (éventuellement filtré par attribut). Le
    déterminisme est scopé: même (scope, type, clair, clé) -> même substitut; un
    scope/type/clé différent dérive un indice distinct (en moyenne).

    Les attributs sont préservés par filtrage préalable du gazetteer:
      - ``gender`` (prénoms): ne garde que les entrées de ``genre`` correspondant;
        si le sous-ensemble est vide (genre inconnu du gazetteer), repli sur le
        gazetteer complet (genre neutre, attribut non préservé, PLAN ligne 561).
      - ``departement`` (communes): ne garde que les communes du département.

    La valeur claire n'est jamais persistée (invariant 1): ``pick`` calcule un
    indice HMAC et renvoie une entrée du gazetteer, sans écrire nulle part.

    Args:
        entity_type: type d'entité (ex. ``"prenom"``, ``"commune"``).
        clear_value: valeur claire à substituer (non stockée).
        scope: identifiant de scope (entre dans le HMAC, déterminisme scopé).
        key: clé HMAC (16, 24 ou 32 bytes, cohérent avec la politique de clé du
            registre phase 10).
        gazetteer: gazetteer embarqué (phase 09) à puiser.
        gender: genre à préserver (``"M"``/``"F"``/``"MF"``) ou ``None``.
        departement: code département à préserver ou ``None``.

    Returns:
        Un ``PickResult`` portant le nom sélectionné et les attributs préservés.

    Raises:
        ValueError: si un argument est invalide (vide, clé non-bytes/taille
            incorrecte, gazetteer vide).
    """
    if not entity_type:
        raise ValueError("entity_type ne peut pas être vide")
    if not clear_value:
        raise ValueError("clear_value ne peut pas être vide")
    if not scope:
        raise ValueError("scope ne peut pas être vide")
    if not isinstance(key, (bytes, bytearray)):
        raise ValueError(f"clé attendue en bytes, reçu {type(key).__name__}")
    if len(key) not in (16, 24, 32):
        raise ValueError(f"longueur de clé {len(key)} invalide: 16, 24 ou 32 bytes")
    if len(gazetteer) == 0:
        raise ValueError("gazetteer vide: aucun substitut disponible")

    # Filtrage par attribut pour préservation (genre / département).
    filtered: list = list(gazetteer)
    if gender is not None:
        filtered = [e for e in filtered if e.genre == gender]
    if departement is not None:
        filtered = [e for e in filtered if e.departement == departement]

    # Repli sur le gazetteer complet si le filtre élimine tout (genre inconnu,
    # département absent). PLAN ligne 561: repli sur genre neutre.
    if not filtered:
        filtered = list(gazetteer)

    n = len(filtered)
    index = _hmac_index(key, scope, entity_type, clear_value, n)
    entry = filtered[index]
    return PickResult(
        name=entry.name,
        gender=entry.genre,
        departement=entry.departement,
    )


def _hmac_index(key: bytes, scope: str, entity_type: str, clear_value: str, n: int) -> int:
    """Indice déterministe dans [0, n) via HMAC-SHA256(key, scope||type||clair).

    Même formule que ``ScopeRegistry._clear_index`` (phase 10) pour cohérence du
    déterminisme scopé. Les 8 premiers octets du digest sont convertis en entier
    big-endian puis réduits mod n.
    """
    msg = (
        scope.encode("utf-8")
        + b"\x00"
        + entity_type.encode("utf-8")
        + b"\x00"
        + clear_value.encode("utf-8")
    )
    digest = hmac.new(bytes(key), msg, hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big") % n
