"""Cipher date par permutation (D8, D22).

Permutation keyée sur [0, N) où N = 201 ans × 12 mois × 28 jours. Le jour est
clampé à [1, 28] avant encodage (28 existe dans tous les mois, garantissant la
réversibilité pour jour <= 28). D8: précision jour non préservée pour jour > 28
(clampé à 28, perte documentée, ré-identifiable par contexte).

Critère 7: le substitut d'une date n'a généralement pas même jour ET même mois
(la permutation mélange jour, mois, année). Le substitut est une date valide
dans la plage [1900-01-01, 2100-12-31].

Formats acceptés: JJ/MM/AAAA et "JJ mois AAAA" (textuel FR, noms en minuscules).
Le format d'entrée est préservé dans le substitut.

Réversibilité: pas de clair stocké. ``decrypt`` parse le substitut, applique
``Permutation.decrypt``, reformate.
"""

from __future__ import annotations

import datetime
import re

from anonyfy.surrogate.permutation import Permutation

_EPOCH_YEAR = 1900
_END_YEAR = 2100
_DAYS_CLAMP = 28  # jour max pour garantie réversibilité (tous mois ont 28)
_MONTHS_PER_YEAR = 12
_N_YEARS = _END_YEAR - _EPOCH_YEAR + 1  # 201
_DOMAIN = _N_YEARS * _MONTHS_PER_YEAR * _DAYS_CLAMP  # 67536

_MONTHS_FR = {
    1: "janvier", 2: "fevrier", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "aout", 9: "septembre", 10: "octobre", 11: "novembre", 12: "decembre",
}
_MONTHS_FR_LOOKUP = {v: k for k, v in _MONTHS_FR.items()}

_SLASH_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_TEXT_RE = re.compile(r"(\d{1,2})\s+(\w+)\s+(\d{4})", re.IGNORECASE)


def _encode(year: int, month: int, day: int) -> int:
    return ((year - _EPOCH_YEAR) * _MONTHS_PER_YEAR + (month - 1)) * _DAYS_CLAMP + (day - 1)


def _decode(index: int) -> tuple[int, int, int]:
    day = index % _DAYS_CLAMP + 1
    rest = index // _DAYS_CLAMP
    month = rest % _MONTHS_PER_YEAR + 1
    year = rest // _MONTHS_PER_YEAR + _EPOCH_YEAR
    return year, month, day


def _parse(value: str) -> tuple[datetime.date, str] | None:
    """Parse une date. Retourne (date_obj, format) où format = 'slash' ou 'text'."""
    m = _SLASH_RE.fullmatch(value)
    if m:
        try:
            d = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
        return d, "slash"
    m = _TEXT_RE.fullmatch(value)
    if m:
        mois = _MONTHS_FR_LOOKUP.get(m.group(2).lower())
        if mois is None:
            return None
        try:
            d = datetime.date(int(m.group(3)), mois, int(m.group(1)))
        except ValueError:
            return None
        return d, "text"
    return None


def _format(year: int, month: int, day: int, fmt: str) -> str:
    if fmt == "slash":
        return f"{day:02d}/{month:02d}/{year}"
    return f"{day} {_MONTHS_FR[month]} {year}"


def _check_range(d: datetime.date) -> bool:
    return datetime.date(_EPOCH_YEAR, 1, 1) <= d <= datetime.date(_END_YEAR, 12, 31)


class DateCipher:
    """Permutation keyée des dates (D8).

    Args:
        key: clé secrète.
        scope: identifiant de scope (déterminisme scopé).
    """

    def __init__(self, key: bytes, scope: str) -> None:
        self._perm = Permutation(key=key, scope=scope, entity_type="date", n=_DOMAIN)

    def encrypt(self, value: str) -> str | None:
        """Retourne le substitut date, ou None si format/plage invalide."""
        parsed = _parse(value)
        if parsed is None:
            return None
        d, fmt = parsed
        if not _check_range(d):
            return None
        day = min(d.day, _DAYS_CLAMP)
        index = _encode(d.year, d.month, day)
        sub_index = self._perm.encrypt(index)
        sy, sm, sd = _decode(sub_index)
        return _format(sy, sm, sd, fmt)

    def decrypt(self, substitute: str) -> str | None:
        """Retourne la date claire (jour clampé si > 28), ou None si invalide."""
        parsed = _parse(substitute)
        if parsed is None:
            return None
        d, fmt = parsed
        if not _check_range(d):
            return None
        sub_index = _encode(d.year, d.month, min(d.day, _DAYS_CLAMP))
        index = self._perm.decrypt(sub_index)
        oy, om, od = _decode(index)
        return _format(oy, om, od, fmt)


__all__ = ["DateCipher"]
