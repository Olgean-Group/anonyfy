"""Tests phase 30 — S4: entité composite code postal / commune.

Le code postal n'est pas masqué alors que la commune l'est: le département réel
fuit et le couple devient incohérent (« 16000 Angoulême » -> « 16000 Fontivillié »).
On traite CP+commune comme une entité composite: le CP est masqué par un CP du
département de la commune substituée (cohérence, PRD §7).

OBJ-REC-109: le CP n'est masqué QUE adjacent à une commune détectée ou après un
déclencheur (``à ``, ``demeurant à ``, ``habite à ``). Un nombre à 5 chiffres
isolé n'est PAS masqué.

Arbitrage OBJ-REC-109: une référence ``\\d{5}`` configurée par le client gagne
sur le CP.
"""

import pytest

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import load_communes
from anonyfy.types import EntityType

_KEY = b"0" * 16


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
    yield v
    v.close()


class TestCPCommuneMasque:
    """CP couplé à une commune: masqué, commune masquée, cohérence dept."""

    def test_cp_et_commune_absents(self, vault):
        """« Il habite à 16000 Angoulême. » -> ni 16000 ni Angoulême."""
        t = "Il habite à 16000 Angoulême."
        m = vault.mask(t)
        assert "16000" not in m.text
        assert "Angoulême" not in m.text

    def test_cp_non_clair(self, vault):
        """Le CP substituté n'est pas le CP clair."""
        m = vault.mask("Il habite à 16000 Angoulême.")
        # Le substitut CP est un nombre à 5 chiffres (pas 16000).
        cp_span = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(cp_span) == 1
        assert cp_span[0].value != "16000"
        assert len(cp_span[0].value) == 5
        assert cp_span[0].value.isdigit()

    def test_cp_apres_trigger_sans_commune(self, vault):
        """CP après déclencheur sans commune adjacente: masqué (OBJ-REC-109)."""
        m = vault.mask("Il habite à 16000.")
        assert "16000" not in m.text

    def test_cp_avant_commune_sans_trigger(self, vault):
        """CP adjacent à une commune sans déclencheur: masqué (couplage)."""
        m = vault.mask("16000 Angoulême")
        assert "16000" not in m.text
        assert "Angoulême" not in m.text


class TestCPIsoleNonMasque:
    """OBJ-REC-109: un nombre à 5 chiffres isolé n'est pas masqué."""

    def test_nombre_isole_non_masque(self, vault):
        """« Le total est 75000 euros » -> 75000 présent."""
        m = vault.mask("Le total est 75000 euros")
        assert "75000" in m.text

    def test_nombre_isole_round_trip(self, vault):
        """Un nombre isolé n'est pas masqué: 75000 présent et round-trip."""
        t = "Le total est 75000 euros"
        m = vault.mask(t)
        # Le CP n'est pas masqué (aucun span CODE_POSTAL).
        cp_spans = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(cp_spans) == 0
        assert "75000" in m.text
        assert vault.unmask(m.text) == t


class TestCoherence:
    """Le CP substitué appartient au département de la commune substituée."""

    def test_coherence_cp_dept_commune(self, vault):
        """Le CP substitué commence par le dept de la commune substituée."""
        m = vault.mask("Il habite à 16000 Angoulême.")
        commune_span = [e for e in m.entities if e.type == EntityType.COMMUNE]
        cp_span = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(commune_span) == 1
        assert len(cp_span) == 1
        commune_sub = commune_span[0].value
        cp_sub = cp_span[0].value
        gaz = load_communes()
        assert commune_sub.casefold() in gaz
        dept = gaz[commune_sub.casefold()].departement
        # Le préfixe CP du département (2A/2B -> "20").
        prefix = "20" if dept in ("2A", "2B") else dept
        assert cp_sub.startswith(prefix), (
            f"CP substitué {cp_sub!r} ne commence pas par le dept {prefix!r} "
            f"de la commune substituée {commune_sub!r}"
        )

    def test_coherence_pas_dept_original(self, vault):
        """Le CP substitué n'appartient pas au département original (16)."""
        m = vault.mask("Il habite à 16000 Angoulême.")
        cp_span = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(cp_span) == 1
        cp_sub = cp_span[0].value
        # Le dept original est 16; le substitut ne doit pas commencer par 16
        # (sauf collision statistique improbable, vérifiée par le test de
        # cohérence ci-dessus qui impose le dept de la commune substituée).
        commune_span = [e for e in m.entities if e.type == EntityType.COMMUNE]
        commune_sub = commune_span[0].value
        gaz = load_communes()
        sub_dept = gaz[commune_sub.casefold()].departement
        sub_prefix = "20" if sub_dept in ("2A", "2B") else sub_dept
        # Si la commune substituée est dans le même dept (16), le CP substitut
        # commence par 16 — c'est cohérent. Sinon, il ne commence pas par 16.
        if sub_prefix != "16":
            assert not cp_sub.startswith("16")


class TestReferenceGagne:
    """OBJ-REC-109: une référence \\d{5} configurée gagne sur le CP."""

    def test_reference_gagne_cp(self, tmp_path):
        """Une référence \\d{5} configurée gagne sur le CP (ne masque pas comme CP)."""
        v = Vault(
            key=_KEY,
            scope="s",
            registry_path=str(tmp_path / "r.db"),
            reference_patterns=[r"\d{5}"],
        )
        t = "Il habite à 16000 Angoulême."
        m = v.mask(t)
        assert "16000" not in m.text
        # Le CP n'est pas masqué comme CP: aucun span CODE_POSTAL.
        cp_spans = [e for e in m.entities if e.type == EntityType.CODE_POSTAL]
        assert len(cp_spans) == 0
        # La référence est masquée comme REFERENCE_DOSSIER.
        ref_spans = [e for e in m.entities if e.type == EntityType.REFERENCE_DOSSIER]
        assert len(ref_spans) == 1
        v.close()

    def test_reference_gagne_round_trip(self, tmp_path):
        """Round-trip avec référence \\d{5} configurée."""
        v = Vault(
            key=_KEY,
            scope="s",
            registry_path=str(tmp_path / "r.db"),
            reference_patterns=[r"\d{5}"],
        )
        t = "Il habite à 16000 Angoulême."
        m = v.mask(t)
        assert v.unmask(m.text) == t
        v.close()


class TestRoundTrip:
    """Réversibilité: mask -> unmask restaure le texte original."""

    def test_round_trip_cp_commune(self, vault):
        """Round-trip « Il habite à 16000 Angoulême. »."""
        t = "Il habite à 16000 Angoulême."
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_round_trip_cp_trigger_sans_commune(self, vault):
        """Round-trip CP après trigger sans commune."""
        t = "Il habite à 16000."
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_round_trip_cp_avant_commune(self, vault):
        """Round-trip CP avant commune."""
        t = "16000 Angoulême"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t

    def test_round_trip_deux_cp_communes(self, vault):
        """Round-trip avec deux couples CP/commune."""
        t = "16000 Angoulême et 75001 Paris"
        m = vault.mask(t)
        assert vault.unmask(m.text) == t
