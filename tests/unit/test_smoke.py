"""Test canari de la phase 02.

Asserte que le paquet ``anonyfy`` est importable. C'est le canari référencé
dans les critères d'acceptation de la phase 02 (``uv run pytest
tests/unit/test_smoke.py`` doit retourner 0). Un test qui ne peut pas échouer
pour une vraie raison est du bruit; on se contente donc de cet import minimal.
"""

import anonyfy


def test_smoke_imports_anonyfy() -> None:
    assert anonyfy.__version__ == "0.1.0"
