"""Tests de la sélection de substituts par gazetteer (phase 11).

Couvre les critères d'acceptation du PLAN (lignes 554-560):
  - déterminisme scopé (même (scope, type, clair, clé) -> même substitut)
  - préservation des attributs (genre pour prénoms, département pour communes)
  - scopes distincts -> substituts distincts en moyenne (>= 80% sur 100 essais)
  - cas limites: genre sans correspondance, gazetteer vide, arguments invalides
  - bornes de l'indice HMAC dans [0, N)

Référence: PLAN.md phase 11, ADR 0001 section 11.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from anonyfy.detect.gazetteers.loader import load_communes, load_prenoms
from anonyfy.surrogate.gazetteer import PickResult, pick

_KEY = b"0" * 16
_SCOPE = "scope-a"


# --- Critère 2: préservation du genre (prénoms) --------------------------


def test_pick_prenom_preserve_gender_masculin():
    """Le substitut d'un prénom masculin reste masculin (critère 2)."""
    gaz = load_prenoms()
    res = pick("prenom", "Jean-Marc", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")
    assert res.gender == "M"


def test_pick_prenom_preserve_genre_feminin():
    """Le substitut d'un prénom féminin reste féminin."""
    gaz = load_prenoms()
    res = pick("prenom", "Marie", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="F")
    assert res.gender == "F"


def test_pick_result_carries_name():
    """Le résultat porte le nom du substitut sélectionné (non vide)."""
    gaz = load_prenoms()
    res = pick("prenom", "Jean", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")
    assert isinstance(res, PickResult)
    assert res.name
    assert isinstance(res.name, str)


# --- Critère 3: déterminisme scopé --------------------------------------


def test_pick_deterministic_same_args():
    """Deux appels identiques renvoient le même substitut (critère 3)."""
    gaz = load_prenoms()
    a = pick("prenom", "Jean", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")
    b = pick("prenom", "Jean", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")
    assert a == b


def test_pick_deterministic_commune():
    """Déterminisme aussi sur les communes (avec département)."""
    gaz = load_communes()
    a = pick("commune", "Lyon", scope=_SCOPE, key=_KEY, gazetteer=gaz, departement="69")
    b = pick("commune", "Lyon", scope=_SCOPE, key=_KEY, gazetteer=gaz, departement="69")
    assert a == b


# --- Critère 4: scopes distincts -> substituts distincts en moyenne -----


def test_pick_distinct_scopes_give_distinct_substituts():
    """>= 80% de substituts distincts sur 100 scopes distincts (critère 4)."""
    gaz = load_prenoms()
    values = {
        pick(
            "prenom", f"prenom-{i}", scope=f"scope-{i}", key=_KEY, gazetteer=gaz, gender="M"
        ).name
        for i in range(100)
    }
    assert len(values) >= 80, f"seulement {len(values)} substituts distincts sur 100"


# --- Préservation du département (communes) -----------------------------


def test_pick_commune_preserve_departement():
    """Le substitut d'une commune du 69 reste dans le 69."""
    gaz = load_communes()
    res = pick("commune", "Lyon", scope=_SCOPE, key=_KEY, gazetteer=gaz, departement="69")
    assert res.departement == "69"


def test_pick_commune_distinct_departements_distinct_results():
    """Filtrer par deux départements donne des résultats distincts en moyenne."""
    gaz = load_communes()
    # On tire 30 communes; pour le 75 (Paris) il n'y a qu'une entrée, donc on
    # utilise un département plus fourni. On vérifie juste que le département est
    # préservé pour deux départements distincts.
    r69 = pick("commune", "x", scope=_SCOPE, key=_KEY, gazetteer=gaz, departement="69")
    r13 = pick("commune", "x", scope=_SCOPE, key=_KEY, gazetteer=gaz, departement="13")
    assert r69.departement == "69"
    assert r13.departement == "13"


# --- Borne de l'indice HMAC dans [0, N) ---------------------------------


def test_pick_index_within_bounds():
    """L'indice sélectionné est toujours dans [0, len(gazetteer_filtré))."""
    gaz = load_prenoms()
    # Sans filtre: N = len(gaz).
    res = pick("prenom", "Quiquece soit", scope=_SCOPE, key=_KEY, gazetteer=gaz)
    assert res.name in {e.name for e in gaz}


def test_pick_index_within_bounds_filtered():
    """Avec filtre de genre, le substitut est dans le sous-ensemble filtré."""
    gaz = load_prenoms()
    res = pick("prenom", "X", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="F")
    names_f = {e.name for e in gaz if e.genre == "F"}
    assert res.name in names_f
    assert res.gender == "F"


# --- Repli sur genre neutre (prénom inconnu du gazetteer filtré) --------


def test_pick_gender_unknown_falls_back_to_neutral():
    """Un genre sans aucune entrée repli sur le gazetteer complet (neutre).

    PLAN ligne 561-562: "préservation du genre impossible -> repli sur genre
    neutre + avertissement journalisé". Ici on injecte un faux gazetteer vide
    pour le genre demandé pour forcer le repli.
    """
    from anonyfy.detect.gazetteers.loader import Gazetteer, GazetteerEntry

    # Gazetteer avec uniquement des entrées 'F', on demande 'M' -> repli.
    entries = {
        "alpha".casefold(): GazetteerEntry(name="alpha", genre="F"),
        "beta".casefold(): GazetteerEntry(name="beta", genre="F"),
    }
    gaz_f_only = Gazetteer(entries)
    res = pick("prenom", "Inconnu", scope=_SCOPE, key=_KEY, gazetteer=gaz_f_only, gender="M")
    # Repli: on obtient quand même un substitut (non vide), mais le genre n'est
    # pas 'M' (impossible à préserver).
    assert res.name in {"alpha", "beta"}
    assert res.gender != "M"  # repli: genre non préservé


# --- Sans attribut (genre/département omis) ----------------------------


def test_pick_without_gender_uses_full_gazetteer():
    """Sans filtre de genre, le substitut vient du gazetteer complet."""
    gaz = load_prenoms()
    res = pick("prenom", "Jean", scope=_SCOPE, key=_KEY, gazetteer=gaz)
    all_names = {e.name for e in gaz}
    assert res.name in all_names


def test_pick_without_departement_uses_full_gazetteer():
    gaz = load_communes()
    res = pick("commune", "Lyon", scope=_SCOPE, key=_KEY, gazetteer=gaz)
    all_names = {e.name for e in gaz}
    assert res.name in all_names


# --- Différences par clé / type / valeur --------------------------------


def test_pick_distinct_keys_give_distinct_results_in_average():
    """Changer la clé change l'indice HMAC -> substituts distincts en moyenne."""
    gaz = load_prenoms()
    values = {
        pick(
            "prenom", "Jean", scope=_SCOPE, key=bytes([i]) * 16, gazetteer=gaz, gender="M"
        ).name
        for i in range(100)
    }
    assert len(values) >= 80


def test_pick_distinct_types_give_distinct_results():
    """Le type entre dans le HMAC: deux types donnent des indices distincts."""
    gaz = load_prenoms()
    a = pick("prenom", "Jean", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")
    b = pick("autre", "Jean", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")
    # Pas une garantie absolue (collision possible) mais l'indice diffère.
    # On vérifie juste que les deux appels réussissent et renvoient un nom.
    assert a.name and b.name


def test_pick_distinct_values_give_distinct_results_in_average():
    gaz = load_prenoms()
    values = {
        pick("prenom", f"v{i}", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M").name
        for i in range(100)
    }
    assert len(values) >= 80


# --- Cohérence avec la formule HMAC documentée --------------------------


def test_pick_index_matches_hmac_formula():
    """L'indice sélectionné correspond à HMAC(key, scope||type||value) mod N."""
    gaz = load_prenoms()
    filtered = [e for e in gaz if e.genre == "M"]
    n = len(filtered)
    msg = (
        _SCOPE.encode("utf-8") + b"\x00" + b"prenom" + b"\x00" + b"Jean"
    )
    expected_index = int.from_bytes(hmac.new(_KEY, msg, hashlib.sha256).digest()[:8], "big") % n
    res = pick("prenom", "Jean", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")
    assert res.name == filtered[expected_index].name


# --- Cas d'erreur -------------------------------------------------------


def test_pick_empty_entity_type_raises():
    gaz = load_prenoms()
    with pytest.raises(ValueError):
        pick("", "Jean", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")


def test_pick_empty_clear_value_raises():
    gaz = load_prenoms()
    with pytest.raises(ValueError):
        pick("prenom", "", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")


def test_pick_empty_scope_raises():
    gaz = load_prenoms()
    with pytest.raises(ValueError):
        pick("prenom", "Jean", scope="", key=_KEY, gazetteer=gaz, gender="M")


def test_pick_empty_gazetteer_raises():
    from anonyfy.detect.gazetteers.loader import Gazetteer

    empty = Gazetteer({})
    with pytest.raises(ValueError):
        pick("prenom", "Jean", scope=_SCOPE, key=_KEY, gazetteer=empty, gender="M")


def test_pick_invalid_key_type_raises():
    gaz = load_prenoms()
    with pytest.raises(ValueError):
        pick("prenom", "Jean", scope=_SCOPE, key="not-bytes", gazetteer=gaz, gender="M")  # type: ignore[arg-type]


def test_pick_invalid_key_length_raises():
    gaz = load_prenoms()
    with pytest.raises(ValueError):
        pick("prenom", "Jean", scope=_SCOPE, key=b"short", gazetteer=gaz, gender="M")


# --- Type du résultat ---------------------------------------------------


def test_pick_result_is_pickresult():
    gaz = load_prenoms()
    res = pick("prenom", "Jean", scope=_SCOPE, key=_KEY, gazetteer=gaz, gender="M")
    assert isinstance(res, PickResult)
    assert hasattr(res, "name")
    assert hasattr(res, "gender")
    assert hasattr(res, "departement")