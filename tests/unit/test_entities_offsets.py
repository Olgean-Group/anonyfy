"""Cohérence des offsets de ``MaskedText.entities`` (D15, phase 13).

Après ``mask``, pour chaque ``entity`` dans ``MaskedText.entities``,
``m.text[entity.start:entity.end]`` doit pointer vers le substitut réel dans
``.text`` (y compris pour des substituts plus longs/courts que l'original).

Le moteur substitue de droite à gauche (architecture §4): les offsets des
substitutions déjà traitées (à droite) ne décalent pas les positions des
substitutions à venir (à gauche), et chaque ``entity`` est enregistrée avec
``start`` (original, inchangé) et ``end = start + len(substitut)``. La cohérence
D15 est donc garantie par construction pour toute longueur de substitut.

Ce test valide le principe sur les types FPE existants (longueur préservée) et
sur des textes multi-types. Le cas « substitut plus long/court » (gazetteer,
dates) est couvert par les tests dédiés ``test_vault_full.py`` une fois le
masquage non-FPE en place (mêmes assertions, offsets cohérents).

Référence: PLAN.md phase 13 (D15), critère 643.
"""

from __future__ import annotations

from anonyfy import Vault


def _vault(tmp_path) -> Vault:
    return Vault(key=b"0" * 16, scope="s", registry_path=str(tmp_path / "off.db"))


class TestOffsetsCoherents:
    def test_siret_offset_pointe_vers_substitut(self, tmp_path) -> None:
        v = _vault(tmp_path)
        m = v.mask("SIRET 73282932000033")
        assert len(m.entities) == 1
        e = m.entities[0]
        assert m.text[e.start : e.end] == e.value
        assert e.value != "73282932000033"

    def test_multi_sirets_offsets_coherents(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "SIRET 73282932000033 et SIRET 41804261100008"
        m = v.mask(t)
        for e in m.entities:
            assert m.text[e.start : e.end] == e.value, (
                f"offset incohérent pour {e.type}: "
                f"text[{e.start}:{e.end}]={m.text[e.start:e.end]!r} != value={e.value!r}"
            )

    def test_mixte_nir_iban_offsets_coherents(self, tmp_path) -> None:
        v = _vault(tmp_path)
        t = "NIR 275032917028004 et IBAN FR7630006000011234567890189"
        m = v.mask(t)
        assert len(m.entities) >= 2
        for e in m.entities:
            assert m.text[e.start : e.end] == e.value

    def test_offsets_croissants_non_chevauchants(self, tmp_path) -> None:
        """Les entities sont triées par position et ne se chevauchent pas."""
        v = _vault(tmp_path)
        m = v.mask("SIRET 73282932000033 et NIR 275032917028004")
        starts = [e.start for e in m.entities]
        assert starts == sorted(starts)
        for a, b in zip(m.entities, m.entities[1:], strict=False):
            assert a.end <= b.start, f"entités chevauchantes: {a} vs {b}"

    def test_invariant_global_toutes_entities(self, tmp_path) -> None:
        """Quel que soit le texte masqué, tout entity pointe vers son substitut."""
        v = _vault(tmp_path)
        for t in [
            "SIRET 73282932000033",
            "NIR 275032917028004 et TVA FR44732829320",
            "CB 4539578743346873 et Tel 0612345678",
            "texte sans identifiant",
        ]:
            m = v.mask(t)
            for e in m.entities:
                assert m.text[e.start : e.end] == e.value, f"échec D15 sur {t!r}"
