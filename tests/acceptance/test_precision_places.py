"""Phase 42 — P1 : précision COMMUNE/VOIE + généralisation de la règle de confiance.

La recette 0.1.4 (P1) : un span COMMUNE ou VOIE à ``confidence < 0.8`` est émis
en ``permissive`` sans indice contextuel, d'où des faux positifs :
« Pierre angulaire du dispositif » (Pierre -> COMMUNE), « Le champ de la mission »
(champ -> VOIE), « douze mois » (douze -> COMMUNE). Une commune en prose (toponyme
de destination, génitif, initiale de phrase) n'est pas une donnée personnelle.

Correctif (D42b/D42c/D42d) : l'invariant généralisé « aucun span < 0.8 sans
indice, quel que soit le type » est posé dans la règle d'émission permissive
(``engine.py``). Indices par type :
- COMMUNE : (a) verbe d'adresse immédiatement avant (``domicilié à ``,
  ``demeurant à ``, ``habite à ``, ``résidant à ``, ``adresse : ``), (b) code
  postal adjacent. PAS de ``à `` nu, PAS de ``de `` nu, PAS de
  majuscule-hors-initiale seule (D42c).
- VOIE : (a) type de voie en tête du span, (b) numéro de rue en tête (D42d).
- Défaut SAFE : un type à ``confidence < 0.8`` sans indice enregistré n'est PAS
  émis en permissive (D42b).

Le correctif porte sur la règle d'émission, pas sur la détection : la confidence
des spans faibles reste 0.5, ``observe`` les montre toujours, ``strict`` lève
toujours dessus (D42a).

Référence : PLAN.md phase 42, D42a-D42f ; critère d'acceptation 1.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.surrogate.engine import _is_bare_candidate
from anonyfy.types import EntityType, Span

_KEY = b"0" * 16
_SCOPE = "acceptance-precision-places"


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


# --- Critère 1 : les 3 faux positifs concrets de la recette + Pierre (génitif).
# Aucun span COMMUNE / VOIE ne doit être émis pour ces phrases (types interdits).
CAS_FAUX_POSITIFS: tuple[tuple[str, tuple[EntityType, ...]], ...] = (
    # Pierre préservé : initiale de phrase sans indice d'adresse (D42e).
    (
        "Pierre angulaire du dispositif, la clause révisée porte sur la gouvernance.",
        (EntityType.COMMUNE,),
    ),
    # Lieu-dit nu sans type de voie : « Le Champ » n'est pas une VOIE.
    ("Le champ de la mission couvre l'audit complet du périmètre.", (EntityType.VOIE,)),
    # « douze » (minuscule) n'est pas une commune.
    ("Le contrat court sur douze mois après la rupture.", (EntityType.COMMUNE,)),
    # « Pierre » en génitif (« de Pierre ») n'est pas une commune (D42c) ; le
    # clair patronymic reste masquable en PRENOM/PATRONYME (R3, D38b).
    ("Le rapport de Pierre a été validé.", (EntityType.COMMUNE,)),
)

# --- Critère 1 : rappel — les vraies communes/voies en contexte d'adresse restent
# masquées (token -> type attendu). Le type et l'invariant F3 sont vérifiés.
CAS_RAPPEL: tuple[tuple[str, str, EntityType], ...] = (
    ("domicilié à Paris", "Paris", EntityType.COMMUNE),
    ("habite à Lyon", "Lyon", EntityType.COMMUNE),
    ("16000 Angoulême", "Angoulême", EntityType.COMMUNE),
    ("12 rue de la Paix", "rue de la Paix", EntityType.VOIE),
)

# --- Critère 1 : communes en prose NON masquées (``à`` nu, ``de`` nu, initiale).
CAS_PRESERVES: tuple[tuple[str, str], ...] = (
    ("Je vais à Paris", "Paris"),
    ("Le train part de Lyon", "Lyon"),
    ("La réunion se tient à Paris", "Paris"),
    # D42e (amendé D45c, phase 45) : une commune en initiale de phrase sans
    # indice d'adresse fort n'est pas masquée (fuite documentée). « Paris, le
    # 23 août 2024. » (en-tête de lettre AVEC date) est désormais MASQUÉ
    # (indice (d) « <Commune>, le <date> », D45h) ; « Paris est la capitale. »
    # (sans date) reste préservé.
    ("Paris est la capitale.", "Paris"),
)


def _span_offsets(m, offset: int):
    """Span émis dont le début (offset masqué) == ``offset`` (None sinon)."""
    for s in m.entities:
        if s.start == offset:
            return s
    return None


class TestFauxPositifsCommunesVoies:
    """Aucun span COMMUNE/VOIE émis pour les faux positifs de la recette."""

    @pytest.mark.parametrize("phrase,types_interdits", CAS_FAUX_POSITIFS)
    def test_aucun_span_du_type_interdit(self, vault, phrase: str, types_interdits) -> None:
        m = vault.mask(phrase)
        problemes = [
            (s.type.value, s.value, round(s.confidence, 2))
            for s in m.entities
            if s.type in types_interdits
        ]
        assert not problemes, f"faux positif {types_interdits} dans {phrase!r}: {problemes}"


class TestRappelAdresses:
    """Les vraies communes/voies en contexte d'adresse restent masquées (D42c/D42d)."""

    @pytest.mark.parametrize("phrase,mot,attendu", CAS_RAPPEL)
    def test_adresse_masquee(self, vault, phrase: str, mot: str, attendu: EntityType) -> None:
        m = vault.mask(phrase)
        assert mot.casefold() not in m.text.casefold(), (
            f"le clair {mot!r} fuit dans {phrase!r} : {m.text!r}"
        )
        offset = phrase.index(mot)
        span = _span_offsets(m, offset)
        assert span is not None, (
            f"aucun span émis pour {mot!r} dans {phrase!r} : "
            f"{[(s.type.value, s.value, s.start) for s in m.entities]}"
        )
        assert span.type == attendu, (
            f"{mot!r} typé {span.type.value} (attendu {attendu.value}) dans {phrase!r}"
        )
        # Invariant F3 : COMMUNE -> mask-commune, VOIE -> mask-voie.
        assert span.rule_id == f"mask-{attendu.value.lower()}", (
            f"F3 violé : {mot!r} substitut {span.rule_id!r} ≠ {attendu.value}"
        )

    def test_demeurant_a_paris_masque(self, vault) -> None:
        """Rappel : « demeurant à Paris » -> Paris est masqué (le clair ne
        franchit pas la frontière, invariant 1).

        NB : le span émis pour « Paris » est PATRONYME, pas COMMUNE : le
        déclencheur TRIGGERS « demeurant » (phase 12) le booste comme patronyme
        (confidence 0.9) et l'arbitrage S3 retire la commune chevauchante. Ce
        typage relève de la détection/arbitrage (hors périmètre D42a, qui ne
        change que la règle d'émission) ; l'indice COMMUNE (D42c) s'applique
        aux spans qui gagnent l'arbitrage en COMMUNE. Le point de sûreté (le
        clair est remplacé) est vérifié ici.
        """
        m = vault.mask("demeurant à Paris")
        assert "Paris" not in m.text, f"« Paris » fuit dans {m.text!r}"
        assert any(s.type in (EntityType.COMMUNE, EntityType.PATRONYME) for s in m.entities), (
            f"aucun substitut émis pour « demeurant à Paris » : {m.entities!r}"
        )


class TestToponymesProsePreserves:
    """Les toponymes de prose (``à`` nu, ``de`` nu, initiale) sont préservés."""

    @pytest.mark.parametrize("phrase,token", CAS_PRESERVES)
    def test_token_present(self, vault, phrase: str, token: str) -> None:
        m = vault.mask(phrase)
        assert token in m.text, f"le toponyme {token!r} a été masqué dans {phrase!r} : {m.text!r}"
        # Aucun span COMMUNE émis pour ce token (il n'est pas une adresse).
        offset = phrase.index(token)
        span = _span_offsets(m, offset)
        assert span is None or span.type is not EntityType.COMMUNE, (
            f"{token!r} masqué COMMUNE dans {phrase!r}"
        )


class TestCommuneInitialeD42e:
    """D42e (amendé D45c, phase 45) : commune en initiale de phrase.

    Sans indice d'adresse fort -> non masquée (« Paris est la capitale. »).
    En-tête de lettre « <Commune>, le <date> » (indice (d), D45h) -> masquée
    COMMUNE (le cas « Paris, le 23 août 2024. » de D42e est renversé).
    """

    def test_paris_capitale_preservee(self, vault) -> None:
        m = vault.mask("Paris est la capitale.")
        assert "Paris" in m.text
        assert not any(s.type == EntityType.COMMUNE for s in m.entities)

    def test_paris_date_masquee_commune(self, vault) -> None:
        """OBJ-105 (D45c) : l'en-tête « Paris, le 23 août 2024. » est masqué
        COMMUNE (F3, condition (b) : règle mask-commune vérifiée)."""
        m = vault.mask("Paris, le 23 août 2024.")
        assert "Paris" not in m.text, f"« Paris » fuit dans {m.text!r}"
        communes = [s for s in m.entities if s.type == EntityType.COMMUNE]
        assert len(communes) == 1, f"attendu 1 span COMMUNE : {m.entities!r}"
        assert communes[0].rule_id == "mask-commune", (
            f"F3 violé : {communes[0].rule_id!r} ≠ mask-commune"
        )


class TestInvariantF3:
    """F3 : un span COMMUNE émis est substitué par une COMMUNE (mask-commune),
    un span VOIE par une VOIE (mask-voie)."""

    def test_commune_substituee_par_commune(self, vault) -> None:
        m = vault.mask("domicilié à Paris")
        communes = [s for s in m.entities if s.type == EntityType.COMMUNE]
        assert len(communes) == 1, f"attendu 1 span COMMUNE : {m.entities!r}"
        assert communes[0].rule_id == "mask-commune"

    def test_voie_substituee_par_voie(self, vault) -> None:
        m = vault.mask("12 rue de la Paix")
        voies = [s for s in m.entities if s.type == EntityType.VOIE]
        assert len(voies) == 1, f"attendu 1 span VOIE : {m.entities!r}"
        assert voies[0].rule_id == "mask-voie"


class TestDefautSafeD42b:
    """D42b : invariant généralisé posé une fois dans la règle d'émission —
    un span à ``confidence < 0.8`` n'est émis en permissive QUE s'il porte un
    indice contextuel enregistré pour son type. Défaut SAFE : un type sans
    indice enregistré est filtré par défaut (pas de chemin silencieux)."""

    def test_type_sans_indice_enregistre_filtre(self) -> None:
        """Un type à 0.5 sans indice enregistré (ici un type « synthétique »
        construit pour le test, hors table des indices de la règle généralisée)
        est un candidat nu : il n'est pas émis en permissive (défaut SAFE)."""
        span = Span(
            start=0,
            end=5,
            type="EMAIL",
            value="mail@ex.fr",
            rule_id="email",
            confidence=0.5,
        )
        assert _is_bare_candidate(span, "mail@ex.fr") is True

    def test_commune_sans_indice_filtree(self) -> None:
        """« à » nu n'est PAS un indice COMMUNE (D42c) : « Je vais à Paris »
        filtre la commune faible."""
        span = Span(
            start=10,
            end=15,
            type="COMMUNE",
            value="Paris",
            rule_id="gazetteer-commune",
            confidence=0.5,
        )
        assert _is_bare_candidate(span, "Je vais à Paris") is True

    def test_commune_avec_indice_emis(self) -> None:
        """Un COMMUNE à 0.5 AVEC indice enregistré (verbe d'adresse avant)
        n'est pas un candidat nu : il est émis (rappel)."""
        span = Span(
            start=12,
            end=17,
            type="COMMUNE",
            value="Paris",
            rule_id="gazetteer-commune",
            confidence=0.5,
        )
        assert _is_bare_candidate(span, "demeurant à Paris") is False
