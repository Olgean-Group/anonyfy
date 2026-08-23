"""Phase 39 — R4 : arbitrage prénom/commune adjacent (D39a-D39e).

La recette 0.1.3 (R4) : certains tokens sont à la fois dans le gazetteer des
prénoms ET dans celui des communes (``Marie``, ``Pierre``, ``Bernard``, ``Paris``…).
L'arbitrage actuel les type COMMUNE (priorité 3 > PRENOM 1 à confiance égale),
ce qui viole l'invariant F3 (substitut de même type) quand le token est en fait
un prénom devant un patronyme : « Mme Marie Lefebvre » -> « Marie » doit être
typé PRENOM (substitut prénom), pas PATRONYME ni COMMUNE.

Règle D39a (fixe) : un token PRENOM+COMMUNE adjacent à un candidat PATRONYME
(ou PRENOM) est typé PRENOM (premier nom) ou PATRONYME (dernier nom), pas
COMMUNE. Une commune n'est presque jamais adjacente à un nom de personne.

Mécanisme (D39b) : pré-filtre dans ``resolve_overlaps`` (miroir du pré-filtre
S3 existant) : pour un token PRENOM+COMMUNE dont un span PATRONYME/PRENOM est
adjacent (une position d'écart, ex. « Marie Lefebvre »), retirer les spans
PATRONYME et COMMUNE du token pour laisser le PRENOM gagner.

Contre-exemples (D39d, non-régression S4) : une commune ambiguë SANS patronyme
adjacent (ex. « Je vais à Paris. », « à Marie ») n'est pas transformée en
PRENOM. Le mécanisme « PRENOM+COMMUNE -> PRENOM par défaut » est REJETÉ
(D39e, destructeur : 360 communes = prénoms, dont ``paris``). D42c (phase 42,
D-commune-strict, décision produit S5) invalide ensuite l'émission COMMUNE sur
« à » nu : en prose sans indice d'adresse fort (verbe d'adresse immédiatement
avant ou CP adjacent), la commune n'est PAS masquée — elle est PRÉSERVÉE.
Ces contre-exemples attestent désormais la préservation (aucun span émis).

Le commit RED (anonyfy 0.1.3) démontre : les formes neutres
« Marie Lefebvre », « Pierre Bernard » sont déjà PRENOM+PATRONYME (correctif
D38a), mais les formes avec titre (« Mme Marie Lefebvre ») ou en liste
(« Présents : Marie Lefebvre ») typent « Marie » PATRONYME (F3 violé) ; les
contre-exemples D39d restent COMMUNE. Le commit GREEN ajoute le pré-filtre
D39a.

Référence : PLAN.md phase 39, D39a-D39e ; PRD R4 ; anonyfy_code_review3.md.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "acceptance-prenom-commune"

# --- Cas positifs R4 : prénom ambigu (prénom+commune) adjacent à un patronyme ---
# Chaque cas = (phrase, [(mot, offset, type attendu), ...]).
# L'offset est la position du mot dans la phrase (vérifiée dans le test).
CASES_POSITIFS: tuple[tuple[str, tuple[tuple[str, int, EntityType], ...]], ...] = (
    # D39c : « Marie Lefebvre » -> « Marie » PRENOM, « Lefebvre » PATRONYME.
    (
        "Marie Lefebvre a signé le contrat.",
        (("Marie", 0, EntityType.PRENOM), ("Lefebvre", 6, EntityType.PATRONYME)),
    ),
    # D39c : « Pierre Bernard » -> « Pierre » PRENOM, « Bernard » PATRONYME.
    (
        "Pierre Bernard est directeur.",
        (("Pierre", 0, EntityType.PRENOM), ("Bernard", 7, EntityType.PATRONYME)),
    ),
    # R4 : titre + prénom+nom — « Marie » reste PRENOM (et non PATRONYME).
    (
        "Mme Marie Lefebvre a signé le contrat.",
        (("Marie", 4, EntityType.PRENOM), ("Lefebvre", 10, EntityType.PATRONYME)),
    ),
    # R4 : liste « Présents : » — idem.
    (
        "Présents : Marie Lefebvre.",
        (("Marie", 11, EntityType.PRENOM), ("Lefebvre", 17, EntityType.PATRONYME)),
    ),
)


# --- Contre-exemples D39d (révisés par D42c, phase 42) : commune ambiguë en
# prose SANS patronyme adjacent ET sans indice d'adresse fort (« à » nu) ->
# PRÉSERVÉE (aucun span COMMUNE émis). Chaque cas = (phrase, mot, offset). ---
CASES_COMMUNES_AMBIGUES: tuple[tuple[str, str, int], ...] = (
    ("Je vais à Paris.", "Paris", 10),
    ("à Marie", "Marie", 2),
)


def _span_a_offset(m, offset: int):
    """Span émis dont le début (offset masqué) == ``offset`` (None sinon)."""
    for s in m.entities:
        if s.start == offset:
            return s
    return None


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


class TestArbitragePrenomCommune:
    """R4 : une commune ambiguë (prénom+commune) adjacente à un patronyme est
    un PRENOM (D39a) ; sans patronyme adjacent ni indice d'adresse fort, elle
    est PRÉSERVÉE, non masquée (D39a + D42c)."""

    @pytest.mark.parametrize("phrase,attentes", CASES_POSITIFS)
    def test_prenom_commune_adjacent(self, vault, phrase: str, attentes) -> None:
        m = vault.mask(phrase)
        for mot, offset, attendu in attentes:
            assert phrase[offset : offset + len(mot)] == mot, "offset corrompu"
            span = _span_a_offset(m, offset)
            assert span is not None, (
                f"aucun span à l'offset {offset} ({mot!r}) dans {phrase!r} : "
                f"{[(s.type.value, s.start, s.value) for s in m.entities]}"
            )
            assert span.type == attendu, (
                f"{mot!r} typé {span.type.value} (attendu {attendu.value}) dans {phrase!r} : "
                f"{[(s.type.value, s.start, s.value) for s in m.entities]}"
            )
            # Invariant F3 : le substitut est de même type que la donnée —
            # le span masqué doit être un substitut du type attendu.
            assert span.rule_id == f"mask-{attendu.value.lower()}", (
                f"F3 violé : {mot!r} substitut {span.rule_id!r} ≠ {attendu.value}"
            )

    @pytest.mark.parametrize("phrase,mot,offset", CASES_COMMUNES_AMBIGUES)
    def test_commune_ambiguë_sans_indice_adresse_préservée(
        self, vault, phrase, mot, offset
    ) -> None:
        """D42c : en prose sans indice d'adresse fort, la commune ambiguë n'est
        pas masquée — elle est PRÉSERVÉE (aucun span COMMUNE émis)."""
        m = vault.mask(phrase)
        assert phrase[offset : offset + len(mot)] == mot, "offset corrompu"
        assert _span_a_offset(m, offset) is None, (
            f"{mot!r} dans {phrase!r} doit être PRÉSERVÉ (aucun span à "
            f"l'offset {offset}), obtenu "
            f"{[(s.type.value, s.start, s.value) for s in m.entities]}"
        )
