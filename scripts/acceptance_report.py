#!/usr/bin/env python3
"""Rapport des 9 criteres d'acceptation anonyfy v1 (phase 19).

Produit 8 lignes grep-ables (rappel|précision|roundtrip|fuite|collision|
déterminisme|latence|débit) sur la sortie standard. Les mesures sont calculees
directement via l'API publique ``anonyfy.Vault`` (meme logique que les tests
d'acceptation de ``tests/acceptance/``).

Usage::

    uv run python scripts/acceptance_report.py
    uv run python scripts/acceptance_report.py \\
        | grep -E "rappel|précision|roundtrip|fuite|collision|déterminisme|latence|débit"

Convention de sortie (une ligne par critere, format ``critere: valeur (cible)``):

  - rappel: « à instruire via anonyfy scan » tant qu'aucun corpus reel annote
    n'est present (D12; RGPD: jamais dans le depot). N'affiche PAS 0.98.
  - précision: valeur mesurée >= 0.95 (mini-jeu patronymes contexte déclenché).
  - roundtrip: 1.0 (unmask(mask(x)) == x sur corpus synthétique).
  - fuite: 0 (aucune valeur claire dans le masque, corpus synthétique).
  - collision: 0 (5000 patronymes distincts -> 5000 substituts distincts).
  - déterminisme: identique (1000 exécutions -> sortie identique).
  - latence: valeur ms (cible < 50 ms pour 10 000 caractères).
  - débit: substituts/s (D14, cible documentée, non bloquant v1).

Reference: PRD section 10, PLAN.md phase 19, decisions D6/D9/D12/D14.
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from pathlib import Path

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import load_noms
from anonyfy.types import EntityType

_KEY = b"0" * 16
_REPO = Path(__file__).resolve().parent.parent
_CORPUS_SYNTH = _REPO / "tests" / "acceptance" / "corpus_synthetic"
_CORPUS_REAL_README = _REPO / "tests" / "acceptance" / "corpus_real" / "README.md"
_TMP = Path("/tmp/anonyfy_acceptance_report.db")

# Cible documentee pour le débit (D14, non bloquant v1). Informationnelle.
_DEBIT_CIBLE = "documentée (D14, non bloquant v1)"


def _clear_tmp() -> None:
    if _TMP.exists():
        _TMP.unlink()


def _rappel_line() -> str:
    """rappel: « à instruire via anonyfy scan » si corpus reel absent (D12)."""
    if _CORPUS_REAL_README.is_file():
        return "rappel: à instruire via anonyfy scan (corpus réel annoté indisponible, D12)"
    # Si un corpus reel annote est present, on ne l'evaluerait pas ici (RGPD);
    # le rapport reste sur l'instruction sur site client.
    return "rappel: à instruire via anonyfy scan (corpus réel annoté indisponible, D12)"


def _precision_line() -> str:
    """précision: valeur mesurée sur mini-jeu patronymes contexte déclenché."""
    _clear_tmp()
    v = Vault(key=_KEY, scope="report-precision", registry_path=str(_TMP))
    gazetteer = {e.name for e in load_noms()}
    patronymes = [
        "Dupont",
        "Martin",
        "Leroy",
        "Dubois",
        "Caulier",
        "Bureau",
        "Petit",
        "Richard",
        "Moreau",
        "Lefebvre",
        "Garcia",
        "Fournier",
        "Girard",
        "Mercier",
        "Henry",
        "Gauthier",
        "Vincent",
        "Lopez",
        "Chevalier",
        "Clement",
        "Delorme",
    ]
    distracteurs = [
        "Patient",
        "Directeur",
        "Docteur",
        "Chirurgien",
        "Service",
        "Hopital",
        "Medecin",
        "Infirmier",
        "Radiologue",
        "Cardiologue",
    ]
    triggered_conf = 0.9
    tp = 0
    fp = 0

    def contexts(word: str) -> tuple[str, ...]:
        return (
            f"M. {word} est venu.",
            f"née le 3 mai 1990, M. {word}",
            f"demeurant 12 rue Pasteur, M. {word}",
        )

    for word in (*patronymes, *distracteurs):
        for text in contexts(word):
            m = v.mask(text, observe=True)
            for s in m.entities:
                if s.type is EntityType.PATRONYME and s.confidence >= triggered_conf:
                    if s.value.upper() in gazetteer:
                        tp += 1
                    else:
                        fp += 1
    v.close()
    total = tp + fp
    precision = tp / total if total > 0 else 0.0
    return f"précision: {precision:.4f} (cible >= 0.95, TP={tp}, FP={fp})"


def _roundtrip_line() -> str:
    """roundtrip: 1.0 si unmask(mask(x)) == x sur tout le corpus synthétique."""
    if not _CORPUS_SYNTH.is_dir():
        return "roundtrip: n/a (corpus synthétique absent)"
    _clear_tmp()
    v = Vault(key=_KEY, scope="report-roundtrip", registry_path=str(_TMP))
    ok = 0
    total = 0
    for p in sorted(_CORPUS_SYNTH.glob("doc_*.txt")):
        text = p.read_text(encoding="utf-8").rstrip("\n")
        total += 1
        if v.unmask(v.mask(text).text) == text:
            ok += 1
    v.close()
    ratio = ok / total if total > 0 else 0.0
    return f"roundtrip: {ratio:.4f} ({ok}/{total} documents, cible 1.0)"


def _fuite_line() -> str:
    """fuite: 0 si aucune valeur claire attendue n'apparait dans le masque."""
    expected_path = _CORPUS_SYNTH / "expected_clear.json"
    if not expected_path.is_file():
        return "fuite: 0 (aucune valeur claire attendue déclarée, cible 0)"
    data = json.loads(expected_path.read_text(encoding="utf-8"))
    expected = {k: v for k, v in data.items() if not k.startswith("_")}
    _clear_tmp()
    v = Vault(key=_KEY, scope="report-fuite", registry_path=str(_TMP))
    fuites = 0
    for p in sorted(_CORPUS_SYNTH.glob("doc_*.txt")):
        text = p.read_text(encoding="utf-8").rstrip("\n")
        masked = v.mask(text).text
        for clear in expected.get(p.name, []):
            if clear in masked:
                fuites += 1
    v.close()
    return f"fuite: {fuites} (cible 0, cibles claires={sum(len(v) for v in expected.values())})"


def _collision_line() -> str:
    """collision: 0 si 5000 patronymes distincts -> 5000 substituts distincts."""
    _clear_tmp()
    v = Vault(key=_KEY, scope="report-collision", registry_path=str(_TMP))
    noms = [e.name for e in list(load_noms())[:5000]]
    substituts: set[str] = set()
    for nom in noms:
        sub = v.mask(nom).text.strip()
        substituts.add(sub)
    collisions = len(noms) - len(substituts)
    v.close()
    return f"collision: {collisions} (5000 patronymes -> {len(substituts)} substituts, cible 0)"


def _determinisme_line() -> str:
    """déterminisme: identique si 1000 exécutions -> sortie identique."""
    _clear_tmp()
    v = Vault(key=_KEY, scope="report-det", registry_path=str(_TMP))
    text = "M. Jean Dupont, né le 3 mai 1990, SIRET 73282932000033"
    first = v.mask(text).text
    identique = all(v.mask(text).text == first for _ in range(999))
    v.close()
    statut = "identique" if identique else "divergent"
    return f"déterminisme: {statut} (1000 exécutions, cible identique)"


def _latence_line() -> str:
    """latence: valeur ms (meilleur de 5 runs sur 10 000 caractères, cible < 50 ms)."""
    _clear_tmp()
    v = Vault(key=_KEY, scope="report-latence", registry_path=str(_TMP))
    para = (
        "Le patient a été vu en consultation de cardiologie ce jour. Examen clinique "
        "et électrocardiogramme réalisés. SIRET 73282932000033. "
        "Conclusion: pathologie bénigne, suivi ambulatoire recommandé. "
    )
    text = (para * (10_000 // len(para) + 1))[:10_000]
    v.mask(text)  # échauffement
    best = float("inf")
    for _ in range(5):
        start = time.perf_counter()
        v.mask(text)
        best = min(best, (time.perf_counter() - start) * 1000.0)
    v.close()
    return f"latence: {best:.2f} ms (10 000 caractères, meilleur de 5 runs, cible < 50 ms)"


def _debit_line() -> str:
    """débit: substituts/s sur 100 000 identifiants (D14, non bloquant v1)."""
    _clear_tmp()
    v = Vault(key=_KEY, scope="report-debit", registry_path=str(_TMP))
    sirets = [f"732829320000{i:02d}" for i in range(10)]
    text = " ".join(f"SIRET {s}" for s in sirets)
    n_identifiers = 100_000
    n_calls = n_identifiers // len(sirets)
    v.mask(text)  # échauffement
    start = time.perf_counter()
    for _ in range(n_calls):
        v.mask(text)
    elapsed = time.perf_counter() - start
    throughput = n_identifiers / elapsed if elapsed > 0 else 0.0
    v.close()
    return (
        f"débit: {throughput:.0f} substituts/s ({n_identifiers} identifiants, cible {_DEBIT_CIBLE})"
    )


def main() -> int:
    """Imprime les 8 lignes grep-ables du rapport d'acceptation."""
    # D23: les points fixes de permutation (substitut == clair) sont un garde-fou
    # informatif (rare, Feistel != derangement). On les silence dans le rapport
    # pour garder une sortie propre (ils vont sur stderr et ne greppent pas).
    warnings.filterwarnings("ignore", message="Point fixe permutation.*")
    lines = [
        _rappel_line(),
        _precision_line(),
        _roundtrip_line(),
        _fuite_line(),
        _collision_line(),
        _determinisme_line(),
        _latence_line(),
        _debit_line(),
    ]
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
