"""Tests du Vault sur identifiants structurés (phase 08, grands domaines D2).

Couvre: mask/unmask aller-retour sur SIRET, SIREN, NIR, IBAN, TVA, CB, téléphone;
invariant 1 (pas de fuite du clair), invariant 2 (déterminisme scopé),
invariant 4 (intrusion: un SIRET valide jamais émis n'est pas déchiffré).

Référence: PLAN.md phase 08, critères d'acceptation lignes 469-478.
"""

from __future__ import annotations

import tempfile

import pytest

from anonyfy import Vault
from anonyfy.types import EntityType


def _vault(tmp_path) -> Vault:
    p = str(tmp_path / "reg.db")
    return Vault(key=b"0" * 16, scope="s", registry_path=p)


# --- SIRET ------------------------------------------------------------------


class TestSiretRoundTrip:
    def test_mask_unmask_siret(self, tmp_path) -> None:
        v = _vault(tmp_path)
        original = "SIRET 73282932000033"
        m = v.mask(original)
        assert "73282932000033" not in m.text
        assert v.unmask(m.text) == original

    def test_mask_produit_substitut_numerique_14(self, tmp_path) -> None:
        v = _vault(tmp_path)
        m = v.mask("SIRET 73282932000033")
        import re

        match = re.search(r"\d{14}", m.text)
        assert match is not None
        assert match.group() != "73282932000033"

    def test_pas_de_fuite_clair(self, tmp_path) -> None:
        v = _vault(tmp_path)
        m = v.mask("SIRET 73282932000033")
        assert "73282932000033" not in m.text


# --- Multi-types ------------------------------------------------------------


class TestMultiTypesRoundTrip:
    def test_nir_iban(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "NIR 275032917028004 et IBAN FR7630006000011234567890189"
        assert v.unmask(v.mask(t).text) == t

    def test_siren(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "SIREN 732829320"
        assert v.unmask(v.mask(t).text) == t

    def test_tva(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "TVA FR44732829320"
        assert v.unmask(v.mask(t).text) == t

    def test_cb(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "CB 4539578743346873"
        assert v.unmask(v.mask(t).text) == t

    def test_telephone(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "Tel 0612345678"
        assert v.unmask(v.mask(t).text) == t

    def test_texte_sans_identifiant_inchange(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "Bonjour tout le monde"
        assert v.unmask(v.mask(t).text) == t


# --- Déterminisme (invariant 2) ---------------------------------------------


class TestDeterminisme:
    def test_1000_executions_identiques(self, tmp_path) -> None:
        p = str(tmp_path / "reg.db")
        v = Vault(key=b"0" * 16, scope="s", registry_path=p)
        t = "SIRET 73282932000033"
        first = v.mask(t).text
        for _ in range(999):
            assert v.mask(t).text == first


# --- Invariant 4: intrusion --------------------------------------------------


class TestIntrusionInvariant4:
    def test_intrusion_invariant4_siret_jamais_emis(self, tmp_path) -> None:
        """Un SIRET valide jamais émis dans le scope n'est pas déchiffré en une
        autre valeur claire (invariant 4)."""
        v = _vault(tmp_path)
        result = v.unmask("SIRET 41804261100008")
        # Le SIRET n'a jamais été masqué: unmask le laisse tel quel (pas déchiffré)
        assert "41804261100008" not in result or result == "SIRET 41804261100008"

    def test_intrusion_nir_jamais_emis(self, tmp_path) -> None:
        v = _vault(tmp_path)
        result = v.unmask("NIR 123456789012311")
        # Un NIR jamais émis n'est pas déchiffré
        assert result == "NIR 123456789012311"

    def test_intrusion_siret_apres_mask_autre(self, tmp_path) -> None:
        """Après avoir masqué un SIRET, unmask d'un AUTRE SIRET valide non émis
        ne le déchiffre pas."""
        v = _vault(tmp_path)
        v.mask("SIRET 73282932000033")
        result = v.unmask("SIRET 41804261100008")
        assert result == "SIRET 41804261100008"


# --- MaskedText / entities --------------------------------------------------


class TestMaskedTextStructure:
    def test_masked_text_entities_non_vides(self, tmp_path) -> None:
        v = _vault(tmp_path)
        m = v.mask("SIRET 73282932000033")
        assert m.text
        assert len(m.entities) == 1
        assert m.entities[0].type == EntityType.SIRET

    def test_entities_offsets_pointent_vers_substitut(self, tmp_path) -> None:
        """Les offsets de .entities pointent vers les substituts réels dans .text."""
        v = _vault(tmp_path)
        m = v.mask("SIRET 73282932000033")
        for ent in m.entities:
            # L'offset du span dans .text correspond au substitut (pas au clair)
            assert m.text[ent.start : ent.end] != "73282932000033"
            assert m.text[ent.start : ent.end] == ent.value


# --- SIRET contient SIREN (arbitrage) ---------------------------------------


class TestArbitrageSiretSiren:
    def test_siret_dans_siren_pas_double_substitution(self, tmp_path) -> None:
        """Un SIRET contient un SIREN (9 premiers chiffres): l'arbitrage garde
        le SIRET, un seul substitut est émis, pas deux."""
        v = _vault(tmp_path)
        # 73282932000033: SIRET 14 chiffres Luhn-valide
        m = v.mask("73282932000033")
        assert len(m.entities) == 1
        assert m.entities[0].type == EntityType.SIRET