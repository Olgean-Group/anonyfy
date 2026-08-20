"""Détection email à alphabet local-part étendu (phase 13, D9).

Le validateur phase 06 (``detect/validators/email.py``) limite la local-part à
``[A-Za-z0-9._+-]`` (pas d'apostrophes ni d'accents), ce qui casse la détection
des emails B2B français (``Jean.O'Brien@…``, ``rené.dupont@…``). D9 exige un
alphabet local-part effectif plus large.

Ce module étend la détection à un alphabet local-part incluant:
  - lettres accentuées (``À-ÿ``);
  - apostrophes ``'`` (U+0027) et ``’`` (U+2019);
  - points ``.``, tirets ``-``, signes ``+``;
  - chiffres et lettres non accentuées.

La normalisation NFKC + minuscules et le masquage FPE de la local-part relèvent
du moteur (phase 13, ``surrogate/``); ce module ne fait que la détection et
renvoie un ``Span`` standard ``EntityType.EMAIL`` dont ``value`` est la raw
capturée (ex. ``Jean.O'Brien@exemple.fr``).

Confiance 0.9 (format seul, pas de clé arithmétique).

Référence: PLAN.md phase 13 (D9, alphabet email pré-autorisé D21).
"""

from __future__ import annotations

import re

from anonyfy.types import EntityType, Span

__all__ = ["detect", "validate"]

# Local-part: lettres (accentuées), chiffres, points, tirets, +, apostrophes
# ' (U+0027) et ’ (U+2019). Le tiret est placé en fin de classe pour éviter
# l'échappement.
_LOCALPART = r"[A-Za-zÀ-ÿ0-9._+'’-]+"
# Domaine: étiquettes séparées par points, au moins deux étiquettes dont une
# extension finale (sous-ensemble RFC 5321).
_DOMAIN = r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"

_EMAIL_FORMAT = re.compile(_LOCALPART + r"@" + _DOMAIN)
_EMAIL_RE = re.compile(r"(?<![A-Za-zÀ-ÿ0-9._+'’-])(" + _LOCALPART + r"@" + _DOMAIN + r")")

_EMAIL_RULE = "email-broad-format"
_CONFIDENCE = 0.9


def validate(value: str) -> bool:
    """True si ``value`` est une adresse email au format attendu (alphabet large)."""
    if not value:
        return False
    return _EMAIL_FORMAT.fullmatch(value) is not None


def detect(text: str) -> list[Span]:
    """Détecte les adresses email (alphabet local-part étendu) dans ``text``."""
    spans: list[Span] = []
    for m in _EMAIL_RE.finditer(text):
        candidate = m.group(1)
        if validate(candidate):
            spans.append(
                Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.EMAIL,
                    value=candidate,
                    rule_id=_EMAIL_RULE,
                    confidence=_CONFIDENCE,
                )
            )
    return spans
