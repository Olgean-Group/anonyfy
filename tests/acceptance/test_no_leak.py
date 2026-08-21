"""Critère d'acceptation 4: aucune fuite du clair dans le texte masqué.

Pour chaque document du corpus synthétique, on masque le texte et on vérifie
qu'aucune valeur claire sensible (listée dans ``expected_clear.json``, connue
par construction) n'apparaît dans le texte masqué. Les libellés (« SIRET »,
« Date », « Mail ») ne sont pas des données personnelles et restent légitimement
présents; on ne les vérifie pas ici.

Référence: PRD §10 critère 4, invariant 1. PLAN.md phase 19, décision D12.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anonyfy import Vault

_KEY = b"0" * 16
_SCOPE = "acceptance-noleak"
_CORPUS = Path(__file__).parent / "corpus_synthetic"
_EXPECTED = _CORPUS / "expected_clear.json"


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


def _load_expected() -> dict[str, list[str]]:
    if not _EXPECTED.is_file():
        return {}
    data = json.loads(_EXPECTED.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _cases() -> list[tuple[str, str, list[str]]]:
    expected = _load_expected()
    cases = []
    for p in sorted(_CORPUS.glob("doc_*.txt")):
        text = p.read_text(encoding="utf-8").rstrip("\n")
        cases.append((p.name, text, expected.get(p.name, [])))
    return cases


@pytest.mark.synthetic
@pytest.mark.parametrize(
    "name,text,clears",
    _cases(),
    ids=[c[0] for c in _cases()],
)
def test_aucune_fuite_clair_dans_masque(vault, name, text, clears):
    """Aucune valeur claire sensible (expected_clear.json) n'apparaît dans m.text."""
    if not clears:
        pytest.skip(f"pas de valeurs claires attendues pour {name}")
    masked = vault.mask(text)
    for clear in clears:
        assert clear not in masked.text, (
            f"fuite: valeur claire {clear!r} présente dans le masqué de {name}: {masked.text!r}"
        )
