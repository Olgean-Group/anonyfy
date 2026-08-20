"""Validateurs arithmétiques d'identifiants (phase 05).

Chaque validateur expose:
  - `validate(value) -> bool`: contrôle arithmétique d'un identifiant candidat;
  - `detect(text) -> list[Span]`: recherche d'identifiants valides dans un texte.

Modules:
  - luhn: algorithme de Luhn (SIREN, SIRET, carte bancaire);
  - mod97: helpers modulo 97 (IBAN, NIR);
  - siren: SIREN (9 chiffres, Luhn) et SIRET (14 chiffres, Luhn);
  - nir: NIR (mod 97, gestion Corse 2A/2B);
  - iban: IBAN France (27 caractères, mod 97);
  - tva: TVA intracommunautaire FR (clé SIREN);
  - cb: carte bancaire (PAN 13-19 chiffres, Luhn).

Référence: PLAN.md phase 05, PRD §7.
"""

from __future__ import annotations

__all__ = ["cb", "iban", "luhn", "mod97", "nir", "siren", "tva"]
