"""Tests du normaliseur de séparateurs moteur (phase 24, B1).

Valide: tokenisation des runs (digits + séparateurs + 2A/2B + préfixe +/FR),
projection par run isolé, table d'offsets, remappage de spans, anti-collage,
empreinte de formatage (template) et réinsertion au unmask.

Référence: PLAN.md phase 24 (B1), OBJ-REC-101/102/105/113.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from anonyfy.detect.normalize import (
    Run,
    build_template,
    reinsert_template,
    tokenize_runs,
)
from anonyfy.types import EntityType


# --- Tokenisation: runs isolés ---------------------------------------------


class TestTokenizeRuns:
    def test_run_simple_sans_separateur(self):
        runs = tokenize_runs("tel 0612345678 fin")
        assert len(runs) == 1
        r = runs[0]
        assert r.projection == "0612345678"
        assert r.original_start == 4
        assert r.original_end == 14

    def test_run_avec_espaces_telephone(self):
        runs = tokenize_runs("tel 06 12 34 56 78")
        assert len(runs) == 1
        assert runs[0].projection == "0612345678"

    def test_run_avec_points_telephone(self):
        runs = tokenize_runs("tel 06.12.34.56.78")
        assert len(runs) == 1
        assert runs[0].projection == "0612345678"

    def test_run_plus_33_conserve_prefixe(self):
        runs = tokenize_runs("tel +33 6 12 34 56 78")
        assert len(runs) == 1
        assert runs[0].projection == "+33612345678"

    def test_run_plus_33_06_normalise_zero_supprime(self):
        # OBJ-REC-113: +33 0X -> +33 X (le 0 est retiré de la projection)
        runs = tokenize_runs("tel +33 06 12 34 56 78")
        assert len(runs) == 1
        assert runs[0].projection == "+33612345678"

    def test_run_FR_prefixe_iban(self):
        runs = tokenize_runs("IBAN FR76 123 456 789 012 345 678 9")
        assert len(runs) == 1
        assert runs[0].projection == "FR761234567890123456789"

    def test_anti_collage_deux_runs_separes_par_texte(self):
        # OBJ-REC-105: 14 rue des Lilas 16000 ne fusionne pas
        runs = tokenize_runs("14 rue des Lilas 16000")
        # Deux runs distincts: "14" et "16000"
        projs = [r.projection for r in runs]
        assert "14" in projs
        assert "16000" in projs
        assert "1416000" not in projs
        # Jamais un run unique fusionné
        assert len(runs) == 2

    def test_anti_collage_chiffres_colles_long(self):
        # 552100554000211234: un seul run, mais la projection == original
        runs = tokenize_runs("552100554000211234")
        assert len(runs) == 1
        assert runs[0].projection == "552100554000211234"

    def test_run_nir_espace_2a_capte_lettres(self):
        # OBJ-REC-102: le run capte 2A/2B
        runs = tokenize_runs("NIR 1 78 02 2A 170 028 004")
        assert len(runs) == 1
        assert runs[0].projection == "178022A170028004"

    def test_offset_table_aligne_projection_et_original(self):
        runs = tokenize_runs("tel 06 12 34 56 78")
        r = runs[0]
        # projection[i] vient de text[offset_table[i]]
        text = "tel 06 12 34 56 78"
        for i, ch in enumerate(r.projection):
            assert text[r.offset_table[i]] == ch

    def test_run_au_moins_deux_chiffres(self):
        # Un run nécessite au moins 2 chiffres
        runs = tokenize_runs("tel 5 fin")
        assert len(runs) == 0


# --- Remappage de spans -----------------------------------------------------


class TestRemapSpans:
    def test_remap_span_vers_positions_originales(self):
        from anonyfy.detect.validators import phone

        runs = tokenize_runs("tel 06 12 34 56 78")
        r = runs[0]
        spans = phone.detect(r.projection)
        assert len(spans) == 1
        # Remap: le span trouvé dans la projection correspond au run entier
        assert spans[0].start == 0
        assert spans[0].end == len(r.projection)
        # La position originale du run
        assert r.original_start == 4
        assert r.original_end == 18


# --- Empreinte de formatage (template) --------------------------------------


class TestTemplate:
    def test_template_telephone_espaces(self):
        text = "tel 06 12 34 56 78"
        runs = tokenize_runs(text)
        r = runs[0]
        # Le span couvre toute la projection
        tmpl = build_template(text, r, 0, len(r.projection))
        # La réinsertion du clair compact redonne la forme séparée
        assert reinsert_template("0612345678", tmpl) == "06 12 34 56 78"

    def test_template_telephone_points(self):
        text = "tel 06.12.34.56.78"
        runs = tokenize_runs(text)
        r = runs[0]
        tmpl = build_template(text, r, 0, len(r.projection))
        assert reinsert_template("0612345678", tmpl) == "06.12.34.56.78"

    def test_template_plus_33_avec_zero(self):
        # OBJ-REC-113: le 0 supprimé est restitué par le template
        text = "tel +33 06 12 34 56 78"
        runs = tokenize_runs(text)
        r = runs[0]
        tmpl = build_template(text, r, 0, len(r.projection))
        # clear = projection compacte (+33612345678)
        assert reinsert_template("+33612345678", tmpl) == "+33 06 12 34 56 78"

    def test_template_plus_33_sans_zero(self):
        text = "tel +33 6 12 34 56 78"
        runs = tokenize_runs(text)
        r = runs[0]
        tmpl = build_template(text, r, 0, len(r.projection))
        assert reinsert_template("+33612345678", tmpl) == "+33 6 12 34 56 78"

    def test_template_siret_groupe(self):
        text = "SIRET 552 100 554 00021"
        runs = tokenize_runs(text)
        r = runs[0]
        tmpl = build_template(text, r, 0, len(r.projection))
        assert reinsert_template("55210055400021", tmpl) == "552 100 554 00021"

    def test_template_nir_espace_2a(self):
        # OBJ-REC-102: 2A restitué
        text = "NIR 1 78 02 2A 170 028 004"
        runs = tokenize_runs(text)
        r = runs[0]
        tmpl = build_template(text, r, 0, len(r.projection))
        # clear = forme substituée (2A -> 19): 1780219170028004
        assert reinsert_template("1780219170028004", tmpl) == "1 78 02 2A 170 028 004"

    def test_template_nir_contigu_2a(self):
        text = "NIR 275032A17028004"
        runs = tokenize_runs(text)
        r = runs[0]
        tmpl = build_template(text, r, 0, len(r.projection))
        assert reinsert_template("275031917028004", tmpl) == "275032A17028004"

    def test_template_iban_espace(self):
        text = "IBAN FR76 123 456 789 012 345 678 9"
        runs = tokenize_runs(text)
        r = runs[0]
        tmpl = build_template(text, r, 0, len(r.projection))
        assert reinsert_template("FR761234567890123456789", tmpl) == "FR76 123 456 789 012 345 678 9"

    def test_template_sans_separateur_renvoie_none(self):
        text = "tel 0612345678"
        runs = tokenize_runs(text)
        r = runs[0]
        tmpl = build_template(text, r, 0, len(r.projection))
        # Pas de séparateurs -> template sans littéraux (None pour économiser)
        assert tmpl is None


# --- Round-trip formes séparées (OBJ-REC-101) -------------------------------


class TestRoundtripSepare:
    """Round-trip mask -> unmask restitue la forme séparée d'origine."""

    @pytest.fixture()
    def vault(self, tmp_path: Path):
        from anonyfy import Vault

        d = tempfile.mkdtemp()
        v = Vault(key=b"0" * 16, scope="s", registry_path=str(Path(d) / "r.db"))
        yield v
        v.close()

    def test_roundtrip_separe_tel_espaces(self, vault):
        m = vault.mask("tel 06 12 34 56 78")
        assert "06 12 34 56 78" not in m.text
        assert vault.unmask(m.text) == "tel 06 12 34 56 78"

    def test_roundtrip_separe_tel_points(self, vault):
        m = vault.mask("tel 06.12.34.56.78")
        assert "06.12.34.56.78" not in m.text
        assert vault.unmask(m.text) == "tel 06.12.34.56.78"

    def test_roundtrip_separe_tel_plus33(self, vault):
        m = vault.mask("tel +33 6 12 34 56 78")
        assert "+33 6 12 34 56 78" not in m.text
        assert vault.unmask(m.text) == "tel +33 6 12 34 56 78"

    def test_roundtrip_separe_nir_espaces(self, vault):
        m = vault.mask("NIR 1 78 03 16 001 234 39")
        assert "1 78 03 16 001 234 39" not in m.text
        assert vault.unmask(m.text) == "NIR 1 78 03 16 001 234 39"

    def test_roundtrip_separe_siret_groupe(self, vault):
        m = vault.mask("SIRET 552 100 554 00021")
        assert "552 100 554 00021" not in m.text
        assert vault.unmask(m.text) == "SIRET 552 100 554 00021"

    def test_roundtrip_separe_iban_espaces(self, vault):
        m = vault.mask("IBAN FR76 123 456 789 012 345 678 9")
        assert "FR76 123 456 789 012 345 678 9" not in m.text
        assert vault.unmask(m.text) == "IBAN FR76 123 456 789 012 345 678 9"


# --- Critères d'acceptation PLAN (no-leak) ---------------------------------


class TestCritereNoLeak:
    @pytest.fixture()
    def vault(self, tmp_path: Path):
        from anonyfy import Vault

        d = tempfile.mkdtemp()
        v = Vault(key=b"0" * 16, scope="s", registry_path=str(Path(d) / "r.db"))
        yield v
        v.close()

    def test_tel_espace_ne_fuit_pas(self, vault):
        m = vault.mask("tel 06 12 34 56 78")
        assert "06 12 34 56 78" not in m.text

    def test_tel_points_ne_fuit_pas(self, vault):
        m = vault.mask("tel 06.12.34.56.78")
        assert "06.12.34.56.78" not in m.text

    def test_tel_plus33_ne_fuit_pas(self, vault):
        m = vault.mask("tel +33 6 12 34 56 78")
        assert "+33 6 12 34 56 78" not in m.text

    def test_tel_plus33_06_ne_fuit_pas(self, vault):
        m = vault.mask("tel +33 06 12 34 56 78")
        assert "+33 06 12 34 56 78" not in m.text

    def test_nir_espace_ne_fuit_pas(self, vault):
        m = vault.mask("NIR 1 78 03 16 001 234 39")
        assert "1 78 03 16 001 234 39" not in m.text

    def test_nir_2a_contigu_ne_fuit_pas(self, vault):
        m = vault.mask("NIR 275032A17028004")
        assert "275032A17028004" not in m.text

    def test_nir_2a_espaces_ne_fuit_pas(self, vault):
        m = vault.mask("NIR 1 78 02 2A 170 028 004")
        assert "1 78 02 2A 170 028 004" not in m.text

    def test_siret_groupe_ne_fuit_pas(self, vault):
        m = vault.mask("SIRET 552 100 554 00021")
        assert "552 100 554 00021" not in m.text

    def test_anti_collage_rue_ne_fuit_pas(self, vault):
        m = vault.mask("14 rue des Lilas 16000")
        assert "1416000" not in m.text

    def test_anti_collage_chiffres_colles_ne_fuit_pas(self, vault):
        m = vault.mask("552100554000211234")
        assert "55210055400021" not in m.text

    def test_12_34_56_78_90_pas_un_siren(self, vault):
        # 10 chiffres: pas un SIREN (9 chiffres). Le texte reste intact.
        m = vault.mask("12 34 56 78 90")
        assert "12 34 56 78 90" in m.text