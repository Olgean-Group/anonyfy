"""Critere d'acceptation 1: rappel >= 98% sur les types structures.

Le rappel (PRD section 10, critere 1) est mesure **uniquement** contre le
corpus reel annote (decision D12/OBJ-017). Un corpus synthetique testerait les
validateurs concus pour lui et produirait un rappel mecaniquement ~100 %, soit
une surpromesse (D12).

En l'absence de corpus reel annote dans ce depot (donnees personnelles, RGPD,
voir ``corpus_real/README.md``), ce test ``pytest.skip`` avec un message clair
tant qu'aucun corpus n'est instruit sur site client via ``anonyfy scan``
(mode observation, PRD F7, phase 17).

Quand un corpus reel annote est present (>= 50 fichiers ``.txt`` avec leurs
``.ann.jsonl`` correspondants dans ``corpus_real/``), le test mesure le rappel
de la detection sur les types structures (NIR, SIREN, SIRET, IBAN, TVA,
CARTE_BANCAIRE, TELEPHONE, PLAQUE_SIV, REFERENCE_DOSSIER, EMAIL, DATE) et
asserte >= 0.98. Les patronymes/prenoms/communes/voies (gazetteers) sont
exclus du rappel structure (mesures separees: precision patronymes, et rappel
gazetteers non exigible en v1).

Format d'annotation attendu (un ``.txt`` + un ``.ann.jsonl`` par document):
    {"start": 12, "end": 19, "type": "SIRET", "value": "73282932000033"}

Reference: PRD section 10 critere 1, PLAN.md phase 19, decision D12.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anonyfy import Vault
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "acceptance-recall"
_CORPUS = Path(__file__).parent / "corpus_real"
_MIN_DOCS = 50

# Types structures (FPE, grand domaine) soumis au rappel >= 98% (PRD section 10).
# Les types gazetteers (PATRONYME, PRENOM, COMMUNE, VOIE) sont exclus: leur
# rappel depend du taux de couverture du gazetteer, non exigible en v1.
_STRUCTURED_TYPES: frozenset[str] = frozenset(
    {
        EntityType.NIR.value,
        EntityType.SIREN.value,
        EntityType.SIRET.value,
        EntityType.IBAN.value,
        EntityType.TVA.value,
        EntityType.CARTE_BANCAIRE.value,
        EntityType.TELEPHONE.value,
        EntityType.PLAQUE_SIV.value,
        EntityType.REFERENCE_DOSSIER.value,
        EntityType.EMAIL.value,
        EntityType.DATE.value,
    }
)


def _annotations_for(doc_txt: Path) -> list[dict]:
    """Lit les annotations ``.ann.jsonl`` associees a un ``.txt`` (ou vide)."""
    ann = doc_txt.with_suffix(".ann.jsonl")
    if not ann.is_file():
        return []
    out = []
    for line in ann.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _corpus_ready() -> bool:
    """True si le corpus reel annote est present (>= _MIN_DOCS .txt avec .ann.jsonl)."""
    if not _CORPUS.is_dir():
        return False
    txts = sorted(_CORPUS.glob("doc_*.txt"))
    if len(txts) < _MIN_DOCS:
        return False
    # Chaque .txt doit avoir un .ann.jsonl non vide.
    for t in txts:
        if not t.with_suffix(".ann.jsonl").is_file():
            return False
        if not _annotations_for(t):
            return False
    return True


def test_recall_structured_ge_98_on_real_corpus(tmp_path):
    """Rappel >= 98% sur les types structures (corpus reel annote uniquement, D12).

    En l'absence de corpus reel annote (RGPD: jamais dans le depot), le test
    ``pytest.skip`` avec un message renvoyant vers ``anonyfy scan``. Quand un
    corpus est instruit sur site client (>= 50 documents annotes), le test
    mesure le rappel de la detection en mode observation et asserte >= 0.98.
    """
    if not _corpus_ready():
        pytest.skip(
            "corps reel annote indisponible - instruire via anonyfy scan "
            "(mode observation, PRD F7, phase 17); voir corpus_real/README.md"
        )

    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    try:
        true_pos = 0
        false_neg = 0
        for doc_txt in sorted(_CORPUS.glob("doc_*.txt")):
            text = doc_txt.read_text(encoding="utf-8")
            annotations = [
                a for a in _annotations_for(doc_txt) if a.get("type") in _STRUCTURED_TYPES
            ]
            if not annotations:
                continue
            detected = v.mask(text, observe=True).entities
            detected_spans = {(s.start, s.end, s.type.value) for s in detected}
            for ann in annotations:
                key = (ann["start"], ann["end"], ann["type"])
                if key in detected_spans:
                    true_pos += 1
                else:
                    false_neg += 1
    finally:
        v.close()

    total = true_pos + false_neg
    if total == 0:
        pytest.skip("aucune annotation de type structure dans le corpus reel")
    recall = true_pos / total
    assert recall >= 0.98, f"rappel structure {recall:.4f} < 0.98 (TP={true_pos}, FN={false_neg})"
