r"""Phase 45 — R5 : formule « Fait à … » masque le mauvais mot.

La recette 0.1.5 (R5) : dans « Fait à Angoulême, le 12 mars 2026. », le moteur
masque « Fait » comme PATRONYME (le participe passé capitalisé en initiale de
phrase, présent dans le gazetteer noms) et laisse « Angoulême » (la vraie donnée
d'adresse) en clair.

Correctif (PLAN.md phase 45) :

- R5-1 (D45a) : `"fait"` ajouté à ``EXCLUDED_NOMS`` (triggers.py) — le participe
  passé « Fait » n'est JAMAIS émis comme PATRONYME, quel que soit le chemin
  (``gazetteer-nom`` ou ``context-capture``).
- R5-2 (D45b/D45h) : deux nouveaux indices d'adresse COMMUNE dans
  ``_commune_a_indice_adresse`` (engine.py) :
  - (c) ``Fait à <commune>`` : insensible à la casse ET contraint au début de
    ligne (position 0 ou précédé de ``\n``), forme ``(?:^|\n)\s*fait à\s+``
    (D45d). La prose « il est fait à Paris » (minuscule, milieu de phrase) est
    exclue ; « FAIT À Paris » (acte en majuscules) est couvert.
  - (d) ``<Commune>, le <date>`` en début de ligne : la commune est le premier
    token de la ligne ET suivie de ``, le <chiffre>`` (dates en CHIFFRES
    uniquement, D45k). L'amendement D45c renverse l'ancien cas D42e
    « Paris, le 23 août 2024. » (désormais masqué).

Invariant F3 (D45f) : un span COMMUNE émis via ces indices est substitué par
une COMMUNE (``rule_id == "mask-commune"``).

Référence : PLAN.md phase 45, D45a-D45k ; critère d'acceptation 1.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "acceptance-fait-a-commune"


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


def _span_couvrant(m, start: int):
    """Premier span masqué dont l'intervalle [s.start, s.end) couvre ``start``.

    Le substitut est placé au même offset que le clair (substitution
    droite-à-gauche, start inchangé) et est contigu : ``s.start <= start <
    s.end`` suffit à dire que le token clair à ``start`` est ce span.
    """
    for s in m.entities:
        if s.start <= start < s.end:
            return s
    return None


class TestFaitACommune:
    """R5-2 : « Fait à <commune>, le <date> » masque la COMMUNE, préserve « Fait »."""

    def test_fait_a_angouleme_commune(self, vault) -> None:
        """« Fait à Angoulême, le 12 mars 2026. » -> Angoulême COMMUNE,
        « Fait » préservé (ni PATRONYME ni rien)."""
        phrase = "Fait à Angoulême, le 12 mars 2026."
        m = vault.mask(phrase)
        assert "Angoulême" not in m.text, f"la commune fuit dans {m.text!r}"
        assert "Fait" in m.text, f"« Fait » (participe passé) ne doit pas être masqué : {m.text!r}"
        offset = phrase.index("Angoulême")
        span = _span_couvrant(m, offset)
        assert span is not None and span.type == EntityType.COMMUNE, (
            f"Angoulême non typé COMMUNE : {m.entities!r}"
        )
        assert span.rule_id == "mask-commune", f"F3 violé : {span.rule_id!r}"

    def test_entete_ligne_commune_masquee(self, vault) -> None:
        """En-tête de lettre « Angoulême, le 12 mars 2026. » (sans « Fait à »)
        -> Angoulême masqué COMMUNE (indice (d), D45c amende D42e)."""
        phrase = "Angoulême, le 12 mars 2026."
        m = vault.mask(phrase)
        assert "Angoulême" not in m.text, f"l'en-tête fuit dans {m.text!r}"
        offset = phrase.index("Angoulême")
        span = _span_couvrant(m, offset)
        assert span is not None and span.rule_id == "mask-commune", (
            f"en-tête non masqué COMMUNE : {m.entities!r}"
        )

    def test_fait_a_majuscules_masque(self, vault) -> None:
        """« FAIT À Paris, le 12 mars 2026. » -> « Paris » masqué COMMUNE
        (indice (c) insensible à la casse, D45d)."""
        phrase = "FAIT À Paris, le 12 mars 2026."
        m = vault.mask(phrase)
        assert "Paris" not in m.text, f"« Paris » fuit dans {m.text!r}"
        assert "FAIT" in m.text, f"« FAIT » ne doit pas être masqué : {m.text!r}"
        offset = phrase.index("Paris")
        span = _span_couvrant(m, offset)
        assert span is not None and span.rule_id == "mask-commune", (
            f"« Paris » non masqué COMMUNE : {m.entities!r}"
        )


class TestNonRegressionD45d:
    """R5-2 non-régression : la prose et le « à » nu restent préservés."""

    def test_je_vais_a_paris_preserve(self, vault) -> None:
        """D-commune-strict : « Je vais à Paris » (prose, verbe de mouvement)
        -> « Paris » PRÉSERVÉ (D45e)."""
        m = vault.mask("Je vais à Paris")
        assert "Paris" in m.text, f"« Paris » masqué à tort : {m.text!r}"

    def test_prose_il_est_fait_a_paris_preserve(self, vault) -> None:
        """« il est fait à Paris la semaine prochaine » (prose, minuscule en
        milieu de phrase) -> « Paris » PRÉSERVÉ (D45d : indice (c) contraint au
        début de ligne)."""
        phrase = "il est fait à Paris la semaine prochaine"
        m = vault.mask(phrase)
        assert "Paris" in m.text, f"prose « fait à » sur-masque : {m.text!r}"


class TestR5_1FaitExclu:
    """R5-1 (D45a) : « fait » ajouté à EXCLUDED_NOMS -> « Fait » jamais PATRONYME."""

    def test_m_fait_pas_patronyme(self, vault) -> None:
        """« M. Fait » -> aucun span PATRONYME sur « Fait » (le déclencheur
        « M. » aurait sinon boosté le gazetteer-nom à 0.9)."""
        phrase = "M. Fait"
        m = vault.mask(phrase)
        assert not any(
            s.type in (EntityType.PATRONYME, EntityType.PRENOM) and s.value.casefold() == "fait"
            for s in m.entities
        ), f"« Fait » émis comme prénom/nom : {m.entities!r}"
        assert "Fait" in m.text, f"« Fait » doit rester dans le texte : {m.text!r}"


class TestD45iOBJ106:
    """D45i (OBJ-106) : aucun span PATRONYME nu ne doit gagner contre le span
    COMMUNE de l'indice « Fait à » (invariant F3)."""

    def test_angouleme_pas_patronyme_si_indice_fait_a(self, vault) -> None:
        """« Fait à Angoulême, le 12 mars 2026. » -> aucun span PATRONYME sur
        « Angoulême » ET rule_id == mask-commune (F3 conservé)."""
        phrase = "Fait à Angoulême, le 12 mars 2026."
        m = vault.mask(phrase)
        offset = phrase.index("Angoulême")
        spans = [s for s in m.entities]
        assert not any(s.type == EntityType.PATRONYME and s.start == offset for s in spans), (
            f"« Angoulême » typé PATRONYME : {[(s.type.value, s.start) for s in spans]}"
        )
        commune = [s for s in spans if s.type == EntityType.COMMUNE]
        assert commune and commune[0].rule_id == "mask-commune", (
            f"« Angoulême » n'est pas émis COMMUNE : {m.entities!r}"
        )

    def test_commune_dans_noms_et_communes_typee_commune(self, vault) -> None:
        """« Fait à Bergerac, le 12 mars 2026. » : Bergerac figure dans le
        gazetteer noms ET communes -> le span COMMUNE (indice (c)) doit gagner
        le tie-break (F3 : aucun span PATRONYME émis sur la commune)."""
        phrase = "Fait à Bergerac, le 12 mars 2026."
        m = vault.mask(phrase)
        spans = list(m.entities)
        assert not any(s.type == EntityType.PATRONYME for s in spans), (
            f"commune typée PATRONYME (F3 violé) : {m.entities!r}"
        )
        commune = [s for s in spans if s.type == EntityType.COMMUNE]
        assert commune and commune[0].rule_id == "mask-commune", (
            f"Bergerac non émis COMMUNE : {m.entities!r}"
        )
        assert "Bergerac" not in m.text, f"« Bergerac » fuit dans {m.text!r}"


class TestD45jCPIntercalaire:
    """D45j (OBJ-107) : « Fait à 16000 Angoulême » -> l'indice (b) CP adjacent
    porte le masquage (pas l'indice (c), qui ne franchit pas le CP)."""

    def test_fait_a_cp_commune(self, vault) -> None:
        """« Fait à 16000 Angoulême, le 12 mars 2026. » -> « Angoulême » masqué
        COMMUNE, « Fait » préservé."""
        phrase = "Fait à 16000 Angoulême, le 12 mars 2026."
        m = vault.mask(phrase)
        assert "Angoulême" not in m.text, f"« Angoulême » fuit dans {m.text!r}"
        assert "Fait" in m.text, f"« Fait » ne doit pas être masqué : {m.text!r}"
        offset = phrase.index("Angoulême")
        span = _span_couvrant(m, offset)
        assert span is not None and span.rule_id == "mask-commune", (
            f"Angoulême non émis COMMUNE : {m.entities!r}"
        )
