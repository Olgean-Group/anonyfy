"""Pattern casse par mot (D24).

Classifie la casse d'un texte par mot en pattern compact (U/l/T) et restitue
la casse depuis la forme majuscule du gazetteer. Le pattern ne contient PAS le
clair (invariant 1): uniquement les codes U (majuscule), l (minuscule), T (Title)
séparés par ':'.

Codes:
- ``U``: mot tout majuscule (ex. "MARC").
- ``l``: mot tout minuscule (ex. "marc").
- ``T``: mot Title Case (première lettre majuscule, reste minuscule, ex. "Marc").

Le pattern est stocké dans le registre (colonne ``case_pattern``) pour les types
gazetteer, permettant au unmask de restituer fidèlement la casse originale depuis
la forme majuscule du gazetteer (SIRENE).
"""

from __future__ import annotations


def _classify_word(word: str) -> str:
    """Classifie la casse d'un mot: U, l, ou T."""
    if word.isupper():
        return "U"
    if word.islower():
        return "l"
    # Title Case: première lettre majuscule, reste minuscule
    if word and word[0].isupper() and word[1:].islower():
        return "T"
    # Mixed non fidèle: repli sur T (documenté, limite D24)
    return "T"


def classify_case(text: str) -> str:
    """Retourne le pattern casse par mot (ex. "rue de la Paix" -> "l:l:l:T")."""
    words = text.split()
    return ":".join(_classify_word(w) for w in words)


def _apply_word(word_uc: str, code: str) -> str:
    """Applique le code de casse à un mot majuscule."""
    if code == "U":
        return word_uc
    if code == "l":
        return word_uc.lower()
    # T: Title Case
    return word_uc.title()


def apply_case(gazetteer_name_uc: str, pattern: str) -> str:
    """Restitue la casse depuis la forme majuscule du gazetteer selon le pattern."""
    if not pattern:
        return gazetteer_name_uc
    words_uc = gazetteer_name_uc.split()
    codes = pattern.split(":")
    # Si le nombre de mots diffère (gazetteer != clair), repli: Title Case global
    if len(words_uc) != len(codes):
        return gazetteer_name_uc.title()
    return " ".join(_apply_word(w, c) for w, c in zip(words_uc, codes, strict=True))


__all__ = ["apply_case", "classify_case"]
