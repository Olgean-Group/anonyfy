r"""Normalisation des séparateurs au niveau moteur (phase 24, B1).

Tokenise les runs ``[\d][\d\s.\-]*[\d]`` (au moins 2 chiffres) du texte, en
capturant aussi les tokens ``2A``/``2B`` (NIR Corse, OBJ-REC-102) et un préfixe
``+`` ou ``FR`` immédiatement avant le run (téléphone international, IBAN/TVA).
Chaque run produit SA projection compacte (sans séparateurs) + SA table
d'offsets vers les positions originales. Les validateurs structurés sont
appliqués PAR RUN isolé (OBJ-REC-105: deux runs voisins ne sont jamais fusionnés).

Un ``+`` immédiatement avant le run est conservé dans la projection
(``+33 6 12 34 56 78`` -> ``+33612345678``). La forme ``+33 0X`` est normalisée
en ``+33 X`` (OBJ-REC-113): le ``0`` est retiré de la projection, mais l'empreinte
de formatage le conserve pour la restitution au unmask.

Empreinte de formatage (OBJ-REC-101): ``build_template`` produit un template du
span original où chaque chiffre est un placeholder (consomme un caractère du
clair compact), chaque séparateur (espace/point/tiret) est un littéral (consomme
0), et chaque token ``2A``/``2B`` est un marqueur (consomme 2 caractères du clair
et émet ``2A``/``2B``). ``reinsert_template`` reconstruit la forme séparée depuis
le clair compact + le template. JAMAIS le clair n'est stocké dans le template
(invariant 1): seules des positions/charflags non-clair y figurent.

Référence: PLAN.md phase 24 (B1), OBJ-REC-101/102/105/113.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["Run", "build_template", "reinsert_template", "tokenize_runs"]

# Run: au moins 2 chiffres, séparateurs internes (espaces/points/tirets),
# tokens 2A/2B (NIR Corse) acceptés à l'intérieur.
_RUN_RE = re.compile(r"[\d](?:2A|2B|[\d\s.\-])*[\d]")

# Marqueurs du template (caractères de contrôle non présents dans le texte).
_PLACEHOLDER = "\x00"  # chiffre: consomme 1 char du clair
_MARK_2A = "\x01"  # token 2A: consomme 2 chars du clair, émet "2A"
_MARK_2B = "\x02"  # token 2B: consomme 2 chars du clair, émet "2B"

_SEPARATORS = {" ", ".", "-"}


@dataclass(frozen=True, slots=True)
class Run:
    """Run de chiffres avec sa projection compacte et sa table d'offsets.

    Attributes:
        original_start: indice absolu de début dans le texte original (incluant
            le préfixe ``+``/``FR`` s'il a été capturé).
        original_end: indice absolu de fin (exclusif) dans le texte original.
        projection: forme compacte (préfixe + chiffres + ``2A``/``2B``,
            sans séparateurs). ``+33 0X`` normalisé en ``+33 X`` (le ``0`` retiré).
        offset_table: ``offset_table[i]`` donne la position absolue dans le
            texte original du caractère ``projection[i]``.
    """

    original_start: int
    original_end: int
    projection: str
    offset_table: tuple[int, ...]


def tokenize_runs(text: str) -> list[Run]:
    """Tokenise le texte en runs isolés (OBJ-REC-105: pas de fusion entre runs).

    Renvoie la liste des runs, triés par position. Un run a au moins 2 chiffres.
    Un préfixe ``+`` ou ``FR`` (case-insensitive) immédiatement avant le run est
    capturé (sans être précédé d'un alnum pour éviter les faux positifs).
    """
    runs: list[Run] = []
    for m in _RUN_RE.finditer(text):
        rs, re_ = m.start(), m.end()
        prefix_start = rs
        prefix = ""
        # Préfixe '+' immédiatement avant le run (non précédé d'un digit/'+').
        if rs >= 1 and text[rs - 1] == "+":
            if rs - 2 < 0 or (not text[rs - 2].isdigit() and text[rs - 2] != "+"):
                prefix = "+"
                prefix_start = rs - 1
        # Préfixe 'FR' (case-insensitive) immédiatement avant le run.
        if not prefix and rs >= 2:
            two = text[rs - 2 : rs]
            if two.upper() == "FR" and two[0].isalpha() and two[1].isalpha():
                # Garder le préfixe seulement s'il n'est pas précédé d'un alnum
                # (sinon 'FR' fait partie d'un mot plus large).
                if rs - 3 < 0 or not text[rs - 3].isalnum():
                    prefix = "FR"
                    prefix_start = rs - 2
        _build_run(text, prefix_start, rs, re_, prefix, runs)
    return runs


def _build_run(
    text: str,
    prefix_start: int,
    run_start: int,
    run_end: int,
    prefix: str,
    out: list[Run],
) -> None:
    """Construit un Run depuis le préfixe + la zone de run, avec normalisation."""
    projection: list[str] = []
    offsets: list[int] = []
    # Préfixe capturé (conservé tel quel dans la projection).
    if prefix:
        for k in range(len(prefix)):
            projection.append(prefix[k])
            offsets.append(prefix_start + k)
    # Corps du run: on parcourt les positions originales, on garde digits et
    # tokens 2A/2B, on supprime les séparateurs.
    i = run_start
    while i < run_end:
        tok = text[i : i + 2]
        if tok in ("2A", "2B"):
            projection.append(tok)
            offsets.append(i)
            offsets.append(i + 1)
            i += 2
            continue
        ch = text[i]
        if ch.isdigit():
            projection.append(ch)
            offsets.append(i)
            i += 1
            continue
        # Séparateur: supprimé de la projection.
        i += 1
    proj_str = "".join(projection)
    # Normalisation +33 0X -> +33 X (OBJ-REC-113): retirer le '0' après '+33'.
    if proj_str.startswith("+330") and len(proj_str) > 4:
        idx = offsets[3]  # position originale du '0' à retirer
        del projection[3]
        del offsets[3]
        proj_str = "".join(projection)
        # Marquer le '0' retiré: on l'ajoute comme littéral dans le template plus
        # tard via build_template (position non dans offset_table). Rien à faire
        # ici: la position idx n'est plus dans offsets, donc build_template la
        # traitera comme littéral '0'.
        _ = idx
    out.append(
        Run(
            original_start=prefix_start,
            original_end=run_end,
            projection=proj_str,
            offset_table=tuple(offsets),
        )
    )


def build_template(text: str, run: Run, proj_start: int, proj_end: int) -> str | None:
    """Construit le template de formatage du span [proj_start, proj_end) du run.

    Le template encode la structure non-chiffre du span original (séparateurs,
    ``2A``/``2B``, ``0`` retiré en ``+33 0X``) pour reformatage au unmask.
    Renvoie ``None`` si le span n'a aucun séparateur/token (rien à reformater).

    Le clair n'est JAMAIS stocké dans le template (invariant 1): seuls des
    marqueurs de position (placeholder pour chiffre, marqueur 2A/2B) et les
    séparateurs littéraux y figurent.
    """
    if proj_start >= proj_end:
        return None
    orig_start = run.offset_table[proj_start]
    orig_end = run.offset_table[proj_end - 1] + 1
    kept = set(run.offset_table[proj_start:proj_end])
    template: list[str] = []
    has_literal = False
    pos = orig_start
    while pos < orig_end:
        tok = text[pos : pos + 2]
        if tok in ("2A", "2B") and pos in kept:
            template.append(_MARK_2A if tok == "2A" else _MARK_2B)
            has_literal = True
            pos += 2
            continue
        if pos in kept:
            template.append(_PLACEHOLDER)
        else:
            # Séparateur ou chiffre retiré (+33 0X): littéral.
            template.append(text[pos])
            has_literal = True
        pos += 1
    if not has_literal:
        return None
    return "".join(template)


def reinsert_template(clear: str, template: str | None) -> str:
    """Reconstruit la forme formatée depuis le clair compact et le template.

    Si ``template`` est ``None`` ou vide, renvoie le clair tel quel (rien à
    reformater). Sinon, consomme les caractères du clair pour remplir les
    placeholders (``\\x00``) et les tokens ``2A``/``2B`` (``\\x01``/``\\x02``),
    et émet les séparateurs littéraux tels quels.
    """
    if not template:
        return clear
    out: list[str] = []
    p = 0
    for ch in template:
        if ch == _PLACEHOLDER:
            if p < len(clear):
                out.append(clear[p])
                p += 1
        elif ch == _MARK_2A:
            out.append("2A")
            p += 2
        elif ch == _MARK_2B:
            out.append("2B")
            p += 2
        else:
            out.append(ch)
    return "".join(out)