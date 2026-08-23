"""Tests du chargeur de gazetteers (phase 09) - API publique + empreinte version.

Valide: chargement paresseux, index inversé (membership), attributs (genre pour
prenoms, departement pour communes), gazetteer_version() et GazetteerVersionMismatch.
"""

from __future__ import annotations

import pytest

from anonyfy.detect.gazetteers import loader
from anonyfy.detect.gazetteers.loader import (
    GazetteerVersionMismatch,
    check_gazetteer_version,
    gazetteer_version,
    load_codes_postaux,
    load_communes,
    load_noms,
    load_prenoms,
    load_voies,
)

# --- prenoms ---


def test_prenoms_membership_and_size():
    """Critere 525: 'Jean' in g et len(g) > 100."""
    g = load_prenoms()
    assert "Jean" in g
    assert len(g) > 100


def test_prenoms_genre_attribute():
    """Critere 527: g['Jean'].genre in ('M','F','MF')."""
    g = load_prenoms()
    assert g["Jean"].genre in ("M", "F", "MF")


def test_prenoms_case_insensitive_lookup():
    """La recherche est insensible a la casse (Jean == JEAN)."""
    g = load_prenoms()
    assert "JEAN" in g
    assert g["Jean"].genre == g["JEAN"].genre


def test_prenoms_membership_false_positive_avoided():
    """Un prenom absent n'est pas membre."""
    g = load_prenoms()
    assert "ZZZ_NON_EXISTANT_XYZ" not in g


def test_prenoms_keyerror_on_missing_getitem():
    """g[absent] leve KeyError."""
    g = load_prenoms()
    with pytest.raises(KeyError):
        g["ZZZ_NON_EXISTANT_XYZ"]


# --- noms (patronymes) ---


def test_noms_membership_and_size():
    g = load_noms()
    assert "MARTIN" in g
    assert len(g) > 100


def test_noms_count_attribute():
    """Un patronyme porte son nombre d'occurrences (int)."""
    g = load_noms()
    assert isinstance(g["MARTIN"].count, int)
    assert g["MARTIN"].count > 0


# --- communes ---


def test_communes_membership_and_size():
    g = load_communes()
    assert "Paris" in g
    assert len(g) > 100


def test_communes_departement_attribute():
    """Critere: attribut departement present pour les communes."""
    g = load_communes()
    dep = g["Paris"].departement
    assert isinstance(dep, str)
    assert dep == "75"


def test_communes_code_commune_attribute():
    """Phase 46 (R6): l'attribut code_commune (colonne 1) est lu pour les communes."""
    g = load_communes()
    cc = g["Paris"].code_commune
    assert isinstance(cc, str)
    assert cc == "75056"


# --- codes postaux (phase 46, R6) ---


def test_codes_postaux_coverage():
    """Critere 3 (phase 46): load_codes_postaux() couvre les 35 007 code_commune."""
    m = load_codes_postaux()
    assert len(m) == 35007


def test_codes_postaux_tie_break_multi_cp():
    """D46b: une commune multi-CP -> le plus petit code_postal (tie-break)."""
    m = load_codes_postaux()
    assert m["2A004"] == "20000"  # Ajaccio: 20000/20090/20167 -> 20000


def test_codes_postaux_corse():
    """D46d: Corse 2A/2B, ex. Afa 2A001 -> 20167."""
    m = load_codes_postaux()
    assert m["2A001"] == "20167"


def test_codes_postaux_dom():
    """D46e: DOM 97101 Abymes -> 97139 (tie-break 97139/97142)."""
    m = load_codes_postaux()
    assert m["97101"] == "97139"


def test_codes_postaux_communes_sans_cp_absentes():
    """D46c: Marseille 13055 / Lyon 69123 / Paris 75056 absents (fallback dept)."""
    m = load_codes_postaux()
    assert "13055" not in m
    assert "69123" not in m
    assert "75056" not in m


def test_codes_postaux_angouleme():
    """Angouleme 16015 -> 16000 (cas nominal du R6)."""
    m = load_codes_postaux()
    assert m["16015"] == "16000"


# --- voies ---


def test_voies_membership_and_size():
    g = load_voies()
    assert len(g) > 0


# --- chargement paresseux / cache ---


def test_load_prenoms_is_cached():
    """Chargement paresseux: deux appels retournent le meme objet en memoire."""
    a = load_prenoms()
    b = load_prenoms()
    assert a is b


def test_load_communes_is_cached():
    a = load_communes()
    b = load_communes()
    assert a is b


def test_reset_cache_forces_reload():
    """reset_cache() invalide le cache paresseux."""
    load_prenoms()
    loader.reset_cache()
    a = load_prenoms()
    b = load_prenoms()
    assert a is b


# --- empreinte de version (D5) ---


def test_gazetteer_version_is_nonempty_str():
    """Critere 528: gazetteer_version() -> str non vide."""
    v = gazetteer_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_gazetteer_version_is_stable():
    """L'empreinte est deterministe (meme valeur sur appels repetes)."""
    assert gazetteer_version() == gazetteer_version()


def test_check_version_matches():
    """check_gazetteer_version(empreinte_embarquee) ne leve pas."""
    check_gazetteer_version(gazetteer_version())  # ne doit pas lever


def test_version_mismatch_raises():
    """Critere 529: GazetteerVersionMismatch levee si empreinte stockee differe."""
    with pytest.raises(GazetteerVersionMismatch):
        check_gazetteer_version("empreinte_fausse_pas_du_tout_concordante")


def test_version_mismatch_is_exception():
    """GazetteerVersionMismatch est une exception (importable depuis loader)."""
    assert issubclass(GazetteerVersionMismatch, Exception)


def test_version_mismatch_message_contains_stored_and_current():
    """Le message d'erreur nomme l'empreinte stockee et l'embarquee (diagnostic)."""
    with pytest.raises(GazetteerVersionMismatch) as exc:
        check_gazetteer_version("fausse")
    msg = str(exc.value)
    assert "fausse" in msg
    assert gazetteer_version() in msg
