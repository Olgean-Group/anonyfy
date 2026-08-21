"""Critère d'acceptation 3: round-trip `unmask(mask(x)) == x` sur 100 % du corpus.

Corpus synthétique de non-régression (D12): détermine/round-trip/injectivité,
PAS rappel. On vérifie que `unmask(mask(t)) == t` pour chaque document du corpus
synthétique (`-k synthetic`).

Référence: PRD §10 critère 3, PLAN.md phase 19, décision D12.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anonyfy import Vault

_KEY = b"0" * 16
_SCOPE = "acceptance-roundtrip"
_CORPUS = Path(__file__).parent / "corpus_synthetic"


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


def _synthetic_docs() -> list[tuple[str, str]]:
    """Renvoie (nom_fichier, texte) pour chaque .txt du corpus synthétique."""
    if not _CORPUS.is_dir():
        return []
    docs = []
    for p in sorted(_CORPUS.glob("doc_*.txt")):
        docs.append((p.name, p.read_text(encoding="utf-8").rstrip("\n")))
    return docs


@pytest.mark.synthetic
class TestRoundTripCorpusSynthetic:
    """unmask(mask(x)) == x sur 100 % du corpus synthétique."""

    @pytest.mark.synthetic
    def test_corpus_non_vide(self):
        """Le corpus synthétique doit contenir au moins un document."""
        docs = _synthetic_docs()
        assert len(docs) >= 1, "corpus synthétique vide"

    @pytest.mark.synthetic
    @pytest.mark.parametrize(
        "name,text",
        _synthetic_docs(),
        ids=[d[0] for d in _synthetic_docs()],
    )
    def test_roundtrip_synthetic(self, vault, name, text):
        """unmask(mask(x)) == x pour chaque document du corpus synthétique."""
        m = vault.mask(text)
        assert vault.unmask(m.text) == text, f"round-trip échoue pour {name}"
