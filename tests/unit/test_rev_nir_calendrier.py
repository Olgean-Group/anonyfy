"""Phase 64 — NIR-CALENDRIER : mois invalides acceptés par ``nir.validate``.

Le validateur NIR acceptait tout mois ``\\d{2}``. Les mois NIR valides sont
01-12, plus 20 (nés en France) et 30-31 (nés à l'étranger) pour les numéros
spéciaux utilisés par l'INSEE. Un mois 13-19 ou 32-99 est un faux positif.

Référence: BACKLOG NIR-CALENDRIER, ``src/anonyfy/detect/validators/nir.py``.
"""

from __future__ import annotations

import pytest

from anonyfy.detect.validators.mod97 import nir_control_key
from anonyfy.detect.validators.nir import validate
from anonyfy.types import EntityType

#: Mois NIR valides : 01-12 (naissance), 20 (France), 30-31 (étranger).
MOIS_VALIDES = (
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
    "12",
    "20",
    "30",
    "31",
)

#: Mois invalides : 00, 13-19, 21-29, 32-99.
MOIS_INVALIDES = ("00", "13", "14", "19", "21", "29", "32", "40", "99")


def _nir_avec_mois(mois: str) -> str:
    """Construit un NIR dont la clé est correcte, pour isoler le contrôle du mois."""
    base = f"180{mois}75001123"  # sexe 1, 80, mois, 75, 001, 123
    assert len(base) == 13, base
    key = nir_control_key(base)
    return f"{base}{key:02d}"


class TestMoisValides:
    @pytest.mark.parametrize("mois", MOIS_VALIDES)
    def test_mois_valide_accepte(self, mois):
        nir = _nir_avec_mois(mois)
        assert len(nir) == 15
        assert validate(nir) is True, f"le mois {mois} doit être accepté"


class TestMoisInvalides:
    @pytest.mark.parametrize("mois", MOIS_INVALIDES)
    def test_mois_invalide_rejete(self, mois):
        nir = _nir_avec_mois(mois)
        assert len(nir) == 15
        assert validate(nir) is False, (
            f"le mois {mois} n'est pas un mois NIR valide et doit être rejeté"
        )

    @pytest.mark.parametrize("mois", MOIS_INVALIDES)
    def test_mois_invalide_non_detecte(self, mois):
        from anonyfy.detect.validators.nir import detect

        nir = _nir_avec_mois(mois)
        texte = f"Numéro : {nir}."
        spans = detect(texte)
        assert spans == [], f"faux positif détecté avec le mois {mois}: {spans!r}"


class TestNonRegressionNIR:
    """Les NIR réels du corpus de tests restent détectés."""

    def test_nir_de_reference_detecte(self):
        from anonyfy.detect.validators.nir import detect

        spans = detect("NIR 275032917028004")
        assert len(spans) == 1
        assert spans[0].type == EntityType.NIR
        assert spans[0].value == "275032917028004"

    def test_cle_invalide_toujours_rejetee(self):
        # Même mois valide, clé fausse : rejeté.
        assert validate("275032917028005") is False


class TestFormatValidPourSubstituts:
    """``format_valid`` couvre la plausibilité des substituts FPE (F3-type)."""

    def test_substitut_fpe_avec_mois_chiffre_reste_plausible(self):
        from anonyfy.surrogate import fpe

        substitut = fpe.encrypt_nir("275032917028004", key=b"0" * 16, scope="s")
        from anonyfy.detect.validators.nir import format_valid

        assert format_valid(substitut) is True
        # Et le masquage réel émet bien un substitut plausible.
        import os
        import tempfile

        from anonyfy import Vault

        v = Vault(key=b"0" * 16, scope="s", registry_path=os.path.join(tempfile.mkdtemp(), "r.db"))
        try:
            w = v.mask("NIR 275032917028004")
            sub = next(s.value for s in w.entities if s.type == EntityType.NIR)
            assert format_valid(sub), f"substitut non plausible: {sub}"
            assert v.unmask(w.text) == "NIR 275032917028004"
        finally:
            v.close()

    def test_format_valid_ignore_le_mois(self):
        from anonyfy.detect.validators.mod97 import nir_control_key
        from anonyfy.detect.validators.nir import format_valid

        for mois in ("13", "37", "99"):
            base = f"180{mois}75001123"
            nir = f"{base}{nir_control_key(base):02d}"
            assert format_valid(nir) is True, f"format_valid doit ignorer le mois {mois}"
            assert validate(nir) is False, f"validate doit rejeter le mois {mois}"
