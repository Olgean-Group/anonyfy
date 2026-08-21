"""Mode observation (phase 17, PRD F7).

``observe=True`` sur ``Vault.mask``: detecte les spans, les journalise (audit),
NE SUBSTITUE RIEN. Retourne un ``MaskedText`` dont ``.text`` == texte original
inchangé, ``.entities`` == spans detectes (avec type/value/confidence/rule_id,
non substitues). Le registre n'est PAS peuple (aucun substitut emis).

Reference: PLAN.md phase 17, criteres 1 et 2.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.audit import AuditLog
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "s"


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


class TestObserveTexteInchange:
    """Critere 2: en mode observation, .text == texte original (inchange)."""

    def test_texte_siret_inchange(self, vault):
        original = "SIRET 73282932000033"
        m = vault.mask(original, observe=True)
        assert m.text == original

    def test_observe_ne_substitue_pas(self, vault):
        """Test de qualite: echoue si mask substitue quand meme.

        Si le mode observation etait mal branche et substituait, m.text
        differeait de l'original -> assertion echoue.
        """
        original = "SIRET 73282932000033"
        m = vault.mask(original, observe=True)
        # Le SIRET clair ne doit PAS avoir ete remplace par un substitut FPE.
        assert m.text == original
        assert "73282932000033" in m.text


class TestObserveEntities:
    """Critere 2: .entities contient les spans detectes (non substitues)."""

    def test_entities_contiennent_siret(self, vault):
        m = vault.mask("SIRET 73282932000033", observe=True)
        types = {e.type for e in m.entities}
        assert EntityType.SIRET in types

    def test_entities_pointent_vers_texte_original(self, vault):
        """En observation, les offsets de .entities pointent vers le texte
        original (non substitue). m.text[e.start:e.end] == span value original.
        """
        original = "SIRET 73282932000033"
        m = vault.mask(original, observe=True)
        for e in m.entities:
            assert m.text[e.start : e.end] == e.value


class TestObserveRegistreNonPeuple:
    """Invariant: en mode observation, le registre n'est pas peuple.

    Aucun substitut emis -> le registre ne contient aucune entree. Si un
    substitut etait emis en observation, ce test le detecte et echoue
    (regression de l'invariant).
    """

    def test_aucun_substitut_emis(self, vault):
        vault.mask("SIRET 73282932000033", observe=True)
        subs = list(vault._registry.iter_surrogates())
        assert subs == [], f"registre peuple en mode observation: {subs}"

    def test_unmask_restitue_original_sans_substitut(self, vault):
        """Sans substitut emis, unmask ne trouve rien a dechiffrer -> texte
        original restitue tel quel (invariant 4: rien demasque qui n'ait ete
        masque; observe ne masque rien -> rien a demasquer).
        """
        original = "SIRET 73282932000033"
        vault.mask(original, observe=True)
        assert vault.unmask(original) == original


class TestObserveAudit:
    """En mode observation avec audit fourni, les spans detectes sont
    journalises (meta uniquement, jamais le clair - invariant 1)."""

    def test_audit_journalise_sans_clair(self, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        v = Vault(
            key=_KEY,
            scope=_SCOPE,
            audit=AuditLog(log_path),
            registry_path=str(tmp_path / "reg.db"),
        )
        v.mask("SIRET 73282932000033", observe=True)
        v.close()
        content = open(log_path).read()
        # Le clair ne doit pas figurer dans le journal (invariant 1).
        assert "73282932000033" not in content
