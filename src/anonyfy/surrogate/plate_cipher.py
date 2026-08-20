"""Cipher plaque SIV par permutation (D2, D22).

Les 3 chiffres de la plaque SIV (LL-NNN-LL[L]) sont permutes sur [0, 1000)
via ``Permutation``. Les lettres sont preservées. Le substitut est reformate
en LL-DDD-LL[L] (format-valide).

D2: plaque SIV relève du mécanisme registre (domaine 1000, FPE non applicable
car FF3-1 exige un domaine minimum plus grand). Ici permutation keyée Feistel.

Réversibilité: pas de clair stocké. ``decrypt`` extrait les chiffres du
substitut, applique ``Permutation.decrypt``, reformate.
"""

from __future__ import annotations

import re

from anonyfy.surrogate.permutation import Permutation

# LL-NNN-LL[L], lettres A-H J-N P-T V-Z (I/O/U exclus), pas de SS en préfixe.
_LETTERS = "A-HJ-NP-TV-Z"
_PLATE_RE = re.compile(rf"((?!SS)[{_LETTERS}]{{2}})-(\d{{3}})-([{_LETTERS}]{{2,3}})")

_DOMAIN = 1000  # [0, 1000) pour 3 chiffres


class PlateCipher:
    """Permutation keyée des 3 chiffres d'une plaque SIV.

    Args:
        key: clé secrète.
        scope: identifiant de scope (déterminisme scopé).
    """

    def __init__(self, key: bytes, scope: str) -> None:
        self._perm = Permutation(key=key, scope=scope, entity_type="plate", n=_DOMAIN)

    def _parse(self, value: str) -> tuple[str, int, str] | None:
        m = _PLATE_RE.fullmatch(value)
        if m is None:
            return None
        return m.group(1), int(m.group(2)), m.group(3)

    def encrypt(self, plate: str) -> str | None:
        """Retourne le substitut LL-DDD-LL[L], ou None si format invalide."""
        parsed = self._parse(plate)
        if parsed is None:
            return None
        prefix, digits, suffix = parsed
        sub_digits = self._perm.encrypt(digits)
        return f"{prefix}-{sub_digits:03d}-{suffix}"

    def decrypt(self, substitute: str) -> str | None:
        """Retourne la plaque claire, ou None si format invalide."""
        parsed = self._parse(substitute)
        if parsed is None:
            return None
        prefix, sub_digits, suffix = parsed
        digits = self._perm.decrypt(sub_digits)
        return f"{prefix}-{digits:03d}-{suffix}"


__all__ = ["PlateCipher"]
