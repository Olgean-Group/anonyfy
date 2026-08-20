"""Tests structurels de la phase 03 (documentation).

Ces tests ne vérifient pas la prose; ils vérifient que les décisions tranchées
(D13, D2, D6, OBJ-008, T1) figurent bien dans les artefacts livrés. Un test qui ne
peut pas échouer pour une vraie raison est du bruit; ici, vérifier qu'un document
contient les clauses structurantes exigées empêche d'oublier une décision
(D13/T1/OBJ-008) avant l'implémentation (phase 07+).

Référence: ``.olgenius/PLAN.md`` phase 03, critères d'acceptation.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ADR = REPO / "docs" / "ADR" / "0001-fpe-ff3.md"
README = REPO / "README.md"
PRD = REPO / "PRD.md"


def test_adr_0001_exists() -> None:
    """L'ADR 0001 est le premier livrable de la phase 03 (D13)."""
    assert ADR.is_file(), f"ADR 0001 manquante: {ADR}"


def test_adr_0001_isole_ff3_derriere_surrogate_fpe() -> None:
    """D13: ff3 est isolé derrière surrogate/fpe.py pour rendre le remplacement possible."""
    text = ADR.read_text(encoding="utf-8")
    assert "ff3" in text
    assert "surrogate/fpe.py" in text or "surrogate\\\\fpe.py" in text


def test_adr_0001_politique_remplacement_ff3() -> None:
    """D13/OBJ-019: politique de remplacement de ff3 (maintenance faible, retrait NIST)."""
    text = ADR.read_text(encoding="utf-8")
    assert any(
        token in text.lower() for token in ("remplacement", "replacement", "plan de remplacement")
    ), "Politique de remplacement de ff3 absente de l'ADR 0001"


def test_adr_0001_retrait_nist_mentionne() -> None:
    """D13: le retrait de FF3 du standard NIST (février 2025) est documenté."""
    text = ADR.read_text(encoding="utf-8")
    assert "NIST" in text
    assert "2025" in text


def test_adr_0001_fpe_par_type_registre() -> None:
    """CA-6 (PLAN phase 03): ≥2 lignes mentionnent « plaque SIV » ou « référence de dossier».

    Le critère CA-6 exige ``grep -E "plaque SIV|référence de dossier"`` retourne
    ≥2 lignes (sensible à la casse). Le tableau §4.2 doit donc écrire les types en
    minuscules initiales. On vérifie aussi que chaque sous-chaîne apparaît au
    moins une fois et que le mécanisme registre est mentionné.
    """
    text = ADR.read_text(encoding="utf-8")
    matching_lines = [
        line for line in text.splitlines() if "plaque SIV" in line or "référence de dossier" in line
    ]
    assert len(matching_lines) >= 2, (
        f"CA-6: attendu ≥2 lignes mentionnant 'plaque SIV' ou 'référence de dossier', "
        f"trouvé {len(matching_lines)}"
    )
    assert any("plaque SIV" in line for line in matching_lines)
    assert any("référence de dossier" in line for line in matching_lines)
    assert "registre" in text


def test_adr_0001_fpe_grands_domaines() -> None:
    """D2: NIR/SIREN/SIRET/IBAN/TVA/CB/téléphone traités par FPE pur (grand domaine)."""
    text = ADR.read_text(encoding="utf-8").lower()
    for type_ident in (
        "nir",
        "siren",
        "siret",
        "iban",
        "tva",
        "carte bancaire",
        "téléphone",
    ):
        assert type_ident in text, f"Type {type_ident} non documenté dans l'ADR 0001"


def test_adr_0001_taille_domaine_minimum() -> None:
    """D2/D13: assertion de taille de domaine minimum par type."""
    text = ADR.read_text(encoding="utf-8")
    assert any(
        token in text.lower()
        for token in ("taille de domaine", "domaine minimum", "domaine effectif")
    ), "Assertion de taille de domaine absente de l'ADR 0001"


def test_adr_0001_vecteurs_ff3_1_nist() -> None:
    """D6: vecteurs de test FF3-1 (NIST) référencés (implémentation en phase 07)."""
    text = ADR.read_text(encoding="utf-8")
    assert "FF3-1" in text
    assert any(token in text for token in ("NIST CAVS", "CAVS", "vecteurs"))


def test_adr_0001_obj_008_cohérence_inter_type() -> None:
    """OBJ-008: la cohérence inter-type SIREN/SIRET/TVA non garantie est documentée comme limite."""
    text = ADR.read_text(encoding="utf-8")
    assert "SIREN" in text and "SIRET" in text and "TVA" in text
    assert "cohérence" in text.lower() or "inter-type" in text.lower()


def test_adr_0001_gazetteer_figé() -> None:
    """D5: source+version+SHA-256 du gazetteer figés."""
    text = ADR.read_text(encoding="utf-8")
    assert "SHA-256" in text
    assert "gazetteer" in text.lower()
    assert "version" in text.lower()


def test_adr_0001_migration_registre() -> None:
    """D4: politique de migration du registre (schema_version)."""
    text = ADR.read_text(encoding="utf-8")
    assert "schema_version" in text
    assert "migration" in text.lower()


def test_adr_0001_logging_meta() -> None:
    """D10: politique de logging méta uniquement, jamais le texte."""
    text = ADR.read_text(encoding="utf-8")
    assert "méta" in text.lower() or "jamais le texte" in text.lower()


def test_adr_0001_empreinte_hmac() -> None:
    """D3: empreinte d'audit = HMAC-SHA-256(key, texte_clair)."""
    text = ADR.read_text(encoding="utf-8")
    assert "HMAC" in text


def test_adr_0001_dates_bucket_mois() -> None:
    """D8: dates traitées par bucket de mois (pas par jour)."""
    text = ADR.read_text(encoding="utf-8")
    assert "bucket" in text.lower() or "mois" in text.lower()


def test_adr_0001_email_nfkc() -> None:
    """D9: email local-part normalisé NFKC + minuscules avant FPE."""
    text = ADR.read_text(encoding="utf-8")
    assert "NFKC" in text
    assert "normalisation" in text.lower() or "normaliser" in text.lower()


def test_adr_0001_rotation_reportee_v2() -> None:
    """Rotation de clé hors périmètre v1, reportée à v2 (T1)."""
    text = ADR.read_text(encoding="utf-8")
    assert "rotation" in text.lower()
    assert "v2" in text


def test_readme_reference_adr_0001() -> None:
    """Le README référence l'ADR 0001."""
    text = README.read_text(encoding="utf-8")
    assert "ADR 0001" in text or "adr/0001" in text.lower() or "0001-fpe-ff3" in text.lower()


def test_readme_documente_obj_008() -> None:
    """Le README documente la limite OBJ-008 (cohérence inter-type SIREN/SIRET/TVA)."""
    text = README.read_text(encoding="utf-8")
    assert "SIREN" in text and "SIRET" in text
    assert "cohérence" in text.lower() or "inter-type" in text.lower()


def test_readme_uv_add_present() -> None:
    """Critère PLAN phase 03: la commande d'installation rapide est présente."""
    text = README.read_text(encoding="utf-8")
    assert "uv add anonyfy" in text


def test_prd_rotation_sans_dès_la_v1() -> None:
    """T1: PRD §8 ne promet plus la rotation de clé 'dès la v1'."""
    text = PRD.read_text(encoding="utf-8")
    # La ligne sur la rotation ne doit pas contenir "dès la v1".
    for line in text.splitlines():
        if "rotation" in line.lower() and "clé" in line.lower():
            assert "dès la v1" not in line.lower(), (
                f"La promesse 'dès la v1' sur la rotation de clé doit être retirée: {line!r}"
            )


def test_prd_rotation_mentionne_v2() -> None:
    """T1: la rotation de clé est reportée à v2 dans le PRD."""
    text = PRD.read_text(encoding="utf-8")
    # Au moins une ligne 'rotation' + 'v2' ou le report à v2 est documenté.
    assert "rotation" in text.lower()
    assert "v2" in text


def test_prd_invariant_clair_preserve() -> None:
    """L'amendement T1 préserve l'invariant 1 (jamais de clair stocké)."""
    text = PRD.read_text(encoding="utf-8")
    assert "clair" in text.lower()
    assert "jamais" in text.lower() or "ne stocke jamais" in text.lower()


# --- ADR 0002 (pas de service hébergé) et docs/JURIDIQUE.md (phase 03, partie 2) ---

ADR2 = REPO / "docs" / "ADR" / "0002-pas-de-service-heberge.md"
JURIDIQUE = REPO / "docs" / "JURIDIQUE.md"


def test_adr_0002_exists() -> None:
    """ADR 0002 formalise la décision « pas de service hébergé »."""
    assert ADR2.is_file(), f"ADR 0002 manquante: {ADR2}"


def test_adr_0002_pas_de_service_heberge() -> None:
    """L'ADR 0002 énonce la décision: anonyfy ne sera jamais un service hébergé."""
    text = ADR2.read_text(encoding="utf-8")
    assert "service hébergé" in text.lower()
    assert "jamais" in text.lower()


def test_adr_0002_bibliotheque_livree() -> None:
    """L'ADR 0002 précise que le code est livré comme bibliothèque (pas un service)."""
    text = ADR2.read_text(encoding="utf-8").lower()
    assert "bibliothèque" in text or "bibliotheque" in text


def test_adr_0002_clair_ne_quitte_pas_client() -> None:
    """L'ADR 0002 rappelle l'invariant 1: le clair ne quitte jamais l'infra client."""
    text = ADR2.read_text(encoding="utf-8").lower()
    assert "clair" in text
    assert "client" in text


def test_adr_0002_pas_de_telemetrie() -> None:
    """L'ADR 0002 exclut la télémétrie (aucun appel réseau, fonctionne hors ligne)."""
    text = ADR2.read_text(encoding="utf-8").lower()
    assert "télémétrie" in text or "telemetrie" in text or "télémetrie" in text


def test_juridique_exists() -> None:
    """docs/JURIDIQUE.md est le cadrage juridique honnête (PRD §9)."""
    assert JURIDIQUE.is_file(), f"JURIDIQUE.md manquant: {JURIDIQUE}"


def test_juridique_mentionne_edps() -> None:
    """Critère PLAN phase 03: grep -i 'EDPS' doit trouver le document (EDPS c. CRU)."""
    text = JURIDIQUE.read_text(encoding="utf-8")
    assert "EDPS" in text


def test_juridique_distingue_pseudonymisation_anonymisation() -> None:
    """Le cadrage rappelle que pseudonymisation n'est pas anonymisation au sens RGPD."""
    text = JURIDIQUE.read_text(encoding="utf-8").lower()
    assert "pseudonymisation" in text
    assert "anonymisation" in text
    assert "rgpd" in text


def test_juridique_risque_reidentification_contexte() -> None:
    """Le cadrage mentionne le risque résiduel de ré-identification par contexte."""
    text = JURIDIQUE.read_text(encoding="utf-8").lower()
    assert "ré-identification" in text or "reidentification" in text
    assert "contexte" in text


def test_juridique_renvoi_dpo_client() -> None:
    """Le cadrage renvoie à la responsabilité du DPO client (instruction au cas par cas)."""
    text = JURIDIQUE.read_text(encoding="utf-8").lower()
    assert "dpo" in text or "responsable" in text
