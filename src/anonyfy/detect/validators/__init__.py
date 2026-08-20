"""Validateurs d'identifiants: arithmétiques (phase 05) et de format (phase 06).

Chaque validateur expose:
  - `validate(value) -> bool`: contrôle d'un identifiant candidat;
  - `detect(text) -> list[Span]`: recherche d'identifiants valides dans un texte.

Modules arithmétiques (clé de contrôle, confiance 1.0):
  - luhn: algorithme de Luhn (SIREN, SIRET, carte bancaire);
  - mod97: helpers modulo 97 (IBAN, NIR);
  - siren: SIREN (9 chiffres, Luhn) et SIRET (14 chiffres, Luhn);
  - nir: NIR (mod 97, gestion Corse 2A/2B);
  - iban: IBAN France (27 caractères, mod 97);
  - tva: TVA intracommunautaire FR (clé SIREN);
  - cb: carte bancaire (PAN 13-19 chiffres, Luhn).

Modules de format (sans clé arithmétique, confiance 0.9):
  - phone: téléphone FR (plan de numérotation, préfixe préservé);
  - plate: plaque SIV (LL-NNN-LL[L], exclut I/O/U/SS);
  - date: date calendaire (JJ/MM/AAAA via datetime.date);
  - email: email (syntaxe RFC simple);
  - reference: référence de dossier (regex configurable par le client).

Référence: PLAN.md phases 05 et 06, PRD §7.
"""

from __future__ import annotations

__all__ = [
    "cb",
    "date",
    "email",
    "iban",
    "luhn",
    "mod97",
    "nir",
    "phone",
    "plate",
    "reference",
    "siren",
    "tva",
]
