"""Pattern casse par mot et par segment composé (D24, phase 36).

Classifie la casse d'un texte en pattern compact (U/l/T) et restitue la casse
depuis la forme majuscule du gazetteer. Le pattern ne contient PAS le clair
(invariant 1): uniquement les codes U (majuscule), l (minuscule), T (Title),
séparés par ':' (mots), '-' (segments de trait d'union) et '\'' (segments
d'apostrophe d'article élidé).

Codes:
- ``U``: mot/segment tout majuscule (ex. "MARC").
- ``l``: mot/segment tout minuscule (ex. "marc", particule "sur" de
  "Vernois-sur-Mance", article élidé "l'" de "l'Aisne").
- ``T``: mot/segment Title Case (première lettre majuscule, reste minuscule,
  ex. "Marc", "Vernois", "Aisne").

Phase 36 (B2 résidu): les noms composés (communes « Vernois-sur-Mance »,
« Moÿ-de-l'Aisne », patronymes « Dubois-Bellon ») étaient classés comme un mot
unique et restitués par ``title()``, qui capitalise la lettre APRÈS CHAQUE trait
d'union et apostrophe: la particule en minuscule « sur » devenait « Sur »,
l'article élidé « l' » devenait « L' » (round-trip faux). Désormais le pattern
encode un code par segment composé (séparés par '-' et '\''), et la restitution
applique chaque code au segment correspondant.

Le pattern est stocké dans le registre (colonne ``case_pattern``) pour les types
gazetteer, permettant au unmask de restituer fidèlement la casse originale depuis
la forme majuscule du gazetteer (SIRENE).
"""

from __future__ import annotations


def _classify_word(word: str) -> str:
    """Code de casse d'un mot, segmenté par traits d'union et apostrophes.

    Un mot composé est une séquence de segments de casse indépendants: les
    traits d'union (ex. "Vernois-sur-Mance": Title, minuscule, Title) et les
    apostrophes de l'article élidé (ex. "l'Aisne": minuscule, Title). Chaque
    segment est classifié individuellement; le pattern du mot joint les codes
    par le séparateur original ('-' ou '\'').
    """
    if "-" in word:
        return "-".join(_classify_word(s) for s in word.split("-"))
    if "'" in word:
        parts = word.split("'")
        codes = [_classify_word(s) for s in parts]
        # Article élidé d'une seule lettre capitalisé en tête de nom propre
        # (« L'Auberge », « D'Aurel ») : le « L » isolé est Upper mais code T
        # (capital de début de nom), pas U (formulaire tout en majuscule).
        for i in range(len(parts) - 1):
            if len(parts[i]) == 1 and parts[i].isupper() and codes[i] == "U":
                codes[i] = "T"
        return "'".join(codes)
    if word.isupper():
        return "U"
    if word.islower():
        return "l"
    # Title Case: première lettre majuscule, reste minuscule
    if word and word[0].isupper() and word[1:].islower():
        return "T"
    # Mixed non fidèle (repli documenté, limite D24)
    return "T"


def classify_case(text: str) -> str:
    """Retourne le pattern casse par mot (ex. "rue de la Paix" -> "l:l:l:T").

    Un mot à trait d'union produit un code par segment, joint par '-'
    (ex. "Vernois-sur-Mance" -> "T-l-T").
    """
    words = text.split()
    return ":".join(_classify_word(w) for w in words)


def _apply_word(word: str, code: str) -> str:
    """Applique le code de casse à un mot (éventuellement segmenté par traits).

    Normalise le mot en majuscule d'abord: le gazetteer communes est en Title
    Case (ex. ``Vauchassis``), le gazetteer patronymes est en majuscule
    (ex. ``BELLON``). Quelle que soit la forme d'entrée, le code ``U`` produit un
    mot majuscule, ``l`` un mot minuscule, ``T`` un mot Title Case.

    Un code segmenté (``T-l-T``) est appliqué segment par segment au mot
    segmenté par traits d'union et apostrophes (``l'T``). Si le nombre de
    segments diffère (registre ancien D24: code unique « T » pour un mot à
    traits), repli Title Case global (comportement d'avant le correctif, aucune
    régression).
    """
    for separator in ("-", "'"):
        if separator in code:
            segments_word = word.split(separator)
            segments_code = code.split(separator)
            if len(segments_word) == len(segments_code):
                return separator.join(
                    _apply_word(w, c) for w, c in zip(segments_word, segments_code, strict=True)
                )
            # Pattern segmenté incompatible (forme différente / registre ancien).
            return word.title()
    upper = word.upper()
    if code == "U":
        return upper
    if code == "l":
        return upper.lower()
    # T: Title Case
    return upper.title()


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
