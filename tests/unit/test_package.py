"""Test canari du paquet anonyfy.

Valide que le paquet s'importe et expose ``__version__ == "0.1.2"``.
C'est le seul test fonctionnel de la phase 01 (socle du paquet) : un test qui ne
peut pas échouer pour une vraie raison est du bruit, on ne multiplie donc pas les
tests tautologiques sur les modules vides.
"""


def test_anonyfy_importable_with_version() -> None:
    import anonyfy

    assert anonyfy.__version__ == "0.1.2"
