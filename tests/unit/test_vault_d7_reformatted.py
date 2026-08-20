"""Tests d'intégration D7: round-trip sur sortie reformatée par un mock de modèle.

Le mock de modèle reformate les **substituts** présents dans ``m.text`` (SIRET
groupé par 3, téléphone espacé, IBAN groupé), jamais le clair. ``unmask`` via
l'automate Aho-Corasick retrouve le substitut reformaté et restitue le texte
clair original (invariant 1: le clair ne franchit pas la frontière).

Périmètre phase 08: types structurés FPE uniquement (SIRET, SIREN, NIR, IBAN,
TVA, CB, téléphone). Le patronyme n'est pas couvert en 08 (phase 13).

Référence: PLAN.md phase 08, critères D7/OBJ-030 lignes 476-477.
"""

from __future__ import annotations

import re

from anonyfy import Vault


def _vault(tmp_path) -> Vault:
    p = str(tmp_path / "d7_reg.db")
    return Vault(key=b"0" * 16, scope="s", registry_path=p)


def _reformat_digits(text: str) -> str:
    """Mock de modèle: groupe les suites de chiffres par 3 (espacées)."""

    def group(m: re.Match[str]) -> str:
        digits = m.group(0)
        return " ".join(digits[i : i + 3] for i in range(0, len(digits), 3))

    return re.sub(r"\d{8,}", group, text)


class TestReformattedRoundTrip:
    def test_reformatted_roundtrip_siret(self, tmp_path) -> None:
        """D7/OBJ-030: un SIRET substitut groupé par 3 est retrouvé par
        Aho-Corasick et unmask restitue l'original."""
        v = _vault(tmp_path)
        t = "SIRET 73282932000033"
        m = v.mask(t)
        assert "73282932000033" not in m.text
        reformatted = _reformat_digits(m.text)
        assert "73282932000033" not in reformatted
        assert v.unmask(reformatted) == t

    def test_reformatted_roundtrip_multi_siret(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "SIRET 73282932000033 et SIRET 41804261100008"
        m = v.mask(t)
        reformatted = _reformat_digits(m.text)
        assert v.unmask(reformatted) == t

    def test_reformatted_roundtrip_iban(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "IBAN FR7630006000011234567890189"
        m = v.mask(t)
        reformatted = _reformat_digits(m.text)
        assert v.unmask(reformatted) == t

    def test_reformatted_roundtrip_nir(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "NIR 275032917028004"
        m = v.mask(t)
        reformatted = _reformat_digits(m.text)
        assert v.unmask(reformatted) == t

    def test_reformatted_roundtrip_mixte(self, tmp_path) -> None:
        """Plusieurs types structurés FPE dans le même texte, reformattage
        groupé de tous les chiffres."""
        v = _vault(tmp_path)
        t = "SIRET 73282932000033 et NIR 275032917028004 et IBAN FR7630006000011234567890189"
        m = v.mask(t)
        reformatted = _reformat_digits(m.text)
        assert v.unmask(reformatted) == t

    def test_clair_ne_franchit_pas_frontiere(self, tmp_path) -> None:
        """Invariant 1: le clair n'apparaît jamais dans m.text ni dans la sortie
        reformatée par le mock."""
        v = _vault(tmp_path)
        t = "SIRET 73282932000033"
        m = v.mask(t)
        reformatted = _reformat_digits(m.text)
        assert "73282932000033" not in m.text
        assert "73282932000033" not in reformatted
