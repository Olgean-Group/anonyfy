"""Test de non-régression phase 36 (B2 résid): round-trip communes à trait d'union.

Le résidu round-trip recette (5 lignes fausses sur 2 000, 0,25 %) provient de la
restitution de casse des noms composés à trait d'union : un segment en minuscule
après un trait d'union (particule « de », « sur », « les », « lès », « en »…)
était capitalisé par le repli ``title()`` de ``apply_case`` (``Vernois-sur-Mance``
→ ``Vernois-Sur-Mance``). D36b : le pattern casse (D24) encode désormais un code
par segment de trait d'union (``T-l-T``), restitué fidèlement.

Ce test exerce le round-trip ``unmask(mask(x)) == x`` sur les communes du
gazetteer COG 2026 comportant une particule en minuscule après un trait d'union
ET dont tous les caractères sont tokenisables par le détecteur (``_TOKEN_RE``
``[A-Za-zÀ-ÿ'’-]``) : 7 878 entrées. Les 31 entrées à ligature « œ » (hors classe
de token) sont écartées ici car non masquées par le détecteur (bug de DÉTECTION
distinct, documenté en backlog, hors périmètre B2 casse). Chaque commune est
masquée dans un contexte ``demeurant <CP> <commune>`` (S4). Le corpus est
déterministe (gazetteer figé phase 09, empreinte SHA-256).
"""

from __future__ import annotations

import re

import pytest

from anonyfy import Vault

_KEY = b"0" * 16
_SCOPE = "roundtrip-hyphen-communes"

# Même classe de tokens que le détecteur de communes (places._TOKEN_RE).
_TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ'’-]+")


def _communes_particule() -> list[str]:
    """Communes à particule après trait d'union, tokenisables par le détecteur."""
    from anonyfy.detect.gazetteers.loader import load_communes

    out: list[str] = []
    for e in load_communes():
        name = e.name
        if "-" not in name:
            continue
        segments = name.split("-")
        if not any(seg.islower() for seg in segments[1:]):
            continue
        # Hors périmètre B2: nom non tokenisable (ligature « œ », espaces,
        # parenthèses) → jamais masqué par le détecteur → round-trip trivial.
        if _TOKEN_RE.fullmatch(name) is None:
            continue
        out.append(name)
    return out


@pytest.fixture(scope="module")
def noms() -> list[str]:
    return _communes_particule()


@pytest.fixture(scope="module")
def vault(tmp_path_factory) -> Vault:
    d = tmp_path_factory.mktemp("roundtrip-hyphen")
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(d / "reg.db"))
    yield v
    v.close()


class TestRoundTripHyphenCommunes:
    """unmask(mask(x)) == x sur les communes à particule après trait d'union."""

    def test_corpus_non_vide(self, noms):
        assert len(noms) >= 1000, f"gazetteer: {len(noms)} communes à particule"

    def test_roundtrip_communes_particule(self, vault, noms):
        """Round-trip exact pour toutes les communes à particule.

        Le registre accumule les substituts; les lignes sont concaténées (un CP
        distinct par commune) et démasquées en un seul appel (une construction
        Aho-Corasick au lieu de N). Sans le correctif phase 36, chaque commune
        à part est restituée avec la part capitalisée (``Sur`` au lieu de
        ``sur``) et ce test échoue sur ~100 % des lignes.
        """
        masked_lines: list[str] = []
        for i, commune in enumerate(noms):
            # CP distinct par ligne (déterministe); le CP est couplé à la
            # commune (S4) : le round-trip valide aussi CP + commune ensemble.
            cp = f"{10000 + i:05d}"
            text = f"demeurant {cp} {commune}"
            masked_lines.append(vault.mask(text).text)
        big_masked = "\n".join(masked_lines)
        big_clear = vault.unmask(big_masked)
        clear_lines = big_clear.split("\n")
        assert len(clear_lines) == len(noms), f"nb lignes: {len(clear_lines)} != {len(noms)}"
        failures: list[str] = []
        for i, (commune, line) in enumerate(zip(noms, clear_lines, strict=True)):
            expected = f"demeurant {10000 + i:05d} {commune}"
            if line != expected:
                failures.append(f"ligne {i}: {expected!r} -> {line!r}")
                if len(failures) >= 10:
                    break
        assert not failures, (
            f"{len(failures)} round-trip(s) échoué(s) sur {len(noms)} communes à particule:\n"
            + "\n".join(failures)
        )
