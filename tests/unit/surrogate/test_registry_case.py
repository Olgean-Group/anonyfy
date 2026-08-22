"""Tests D24: flag casse stocké dans le registre (pattern par mot).

Le registre persiste un pattern casse par mot (U/l/T) pour les types gazetteer,
permettant au unmask de restituer fidèlement la casse originale du clair depuis
la forme majuscule du gazetteer. Le pattern ne contient PAS le clair (invariant 1).

Schema v2: colonne ``case_pattern TEXT`` (nullable, NULL pour FPE sans casse).
Migration v1->v2: ALTER TABLE entries ADD COLUMN case_pattern TEXT.
"""

import sqlite3

from anonyfy.surrogate.case_pattern import apply_case, classify_case
from anonyfy.surrogate.registry import CURRENT_SCHEMA_VERSION, ScopeRegistry

_KEY = b"0" * 16


class TestClassifyCase:
    """classify_case retourne un pattern par mot (U/l/T)."""

    def test_uc(self):
        assert classify_case("MARC LEROY") == "U:U"

    def test_lc(self):
        assert classify_case("marc leroy") == "l:l"

    def test_tc(self):
        assert classify_case("Marc Leroy") == "T:T"

    def test_mx_rue_de_la_paix(self):
        assert classify_case("rue de la Paix") == "l:l:l:T"

    def test_mot_unique(self):
        assert classify_case("JEAN") == "U"
        assert classify_case("jean") == "l"
        assert classify_case("Jean") == "T"


class TestApplyCase:
    """apply_case restitue la casse depuis la forme du gazetteer.

    Le gazetteer communes est en Title Case (ex. ``Vauchassis``), le gazetteer
    patronymes est en majuscule (ex. ``BELLON``). ``apply_case`` doit restituer
    la casse d'origine du clair quelle que soit la forme du nom gazetteer fourni
    en entrée: elle normalise en majuscule puis applique le pattern.
    """

    def test_uc(self):
        assert apply_case("MARC LEROY", "U:U") == "MARC LEROY"

    def test_lc(self):
        assert apply_case("MARC LEROY", "l:l") == "marc leroy"

    def test_tc(self):
        assert apply_case("MARC LEROY", "T:T") == "Marc Leroy"

    def test_mx_rue_de_la_paix(self):
        assert apply_case("RUE DE LA PAIX", "l:l:l:T") == "rue de la Paix"

    def test_mot_unique(self):
        assert apply_case("JEAN", "U") == "JEAN"
        assert apply_case("JEAN", "l") == "jean"
        assert apply_case("JEAN", "T") == "Jean"

    def test_entree_title_vers_uc(self):
        """B2a: entrée Title Case (gazetteer communes), code U -> majuscule."""
        assert apply_case("Bellon", "U") == "BELLON"
        assert apply_case("Vauchassis", "U") == "VAUCHASSIS"

    def test_entree_title_vers_lc(self):
        """B2a: entrée Title Case, code l -> minuscule."""
        assert apply_case("Bellon", "l") == "bellon"

    def test_entree_title_vers_tc(self):
        """B2a: entrée Title Case, code T -> Title Case (identique)."""
        assert apply_case("Bellon", "T") == "Bellon"

    def test_entree_minuscule_vers_uc(self):
        """B2a: entrée minuscule, code U -> majuscule."""
        assert apply_case("bellon", "U") == "BELLON"


class TestClassifyCaseHyphen:
    """classify_case segmente aussi sur les traits d'union (phase 36, B2).

    Un mot composé à trait d'union (ex. commune « Vernois-sur-Mance ») n'est
    pas un seul mot de casse homogène : les particules (de, sur, les, la, lès…)
    sont en minuscule entre segments Title Case. Le pattern encode un code par
    segment, séparé par '-'.
    """

    def test_particule_lowercase_apres_tiret(self):
        assert classify_case("Vernois-sur-Mance") == "T-l-T"

    def test_particule_apostrophe_apres_tiret(self):
        assert classify_case("Léguillac-de-l'Auche") == "T-l-l'T"

    def test_article_elide_apostrophe(self):
        assert classify_case("Moÿ-de-l'Aisne") == "T-l-l'T"

    def test_tout_majuscule_tirets(self):
        assert classify_case("BEAUVAIS-LES-BAINS") == "U-U-U"

    def test_title_sans_particule(self):
        assert classify_case("Dubois-Bellon") == "T-T"

    def test_espace_et_tiret(self):
        assert classify_case("Saint-Pierre de la Roche") == "T-T:l:l:T"

    def test_apostrophe_mot_unique(self):
        assert classify_case("L'Auberge") == "T'T"
        assert classify_case("d'Olonne") == "l'T"


class TestApplyCaseHyphen:
    """apply_case : les particules en minuscule après trait d'union sont
    restituées telles quelles (phase 36, B2 résidu round-trip).

    Sans le correctif, « Vernois-sur-Mance » était restitué « Vernois-Sur-Mance »
    (le repli ``title()`` capitalise la lettre après chaque trait d'union).
    """

    def test_particule_lowercase_restituee(self):
        assert apply_case("VERNOIS-SUR-MANCE", "T-l-T") == "Vernois-sur-Mance"

    def test_particule_apostrophe_restituee(self):
        assert apply_case("LÉGUILLAC-DE-L'AUCH", "T-l-l'T") == "Léguillac-de-l'Auch"

    def test_article_elide_restitue(self):
        assert apply_case("MOŸ-DE-L'AISNE", "T-l-l'T") == "Moÿ-de-l'Aisne"

    def test_apostrophe_mot_unique_restitue(self):
        assert apply_case("D'OLONNE", "l'T") == "d'Olonne"
        assert apply_case("L'AUBERGE", "T'T") == "L'Auberge"

    def test_tout_majuscule_restitue(self):
        assert apply_case("BEAUARD-LES-BAINS", "U-U-U") == "BEAUARD-LES-BAINS"

    def test_title_segments_majuscules(self):
        assert apply_case("BEAUARD-LES-BAINS", "T-T-T") == "Beauard-Les-Bains"

    def test_pattern_ancien_sans_tiret_retrocompat(self):
        # Un registre ancien (D24) a stocké un code unique « T » pour un mot à
        # trait d'union: le repli title() s'applique (comportement d'avant).
        assert apply_case("VERNOIS-SUR-MANCE", "T") == "Vernois-Sur-Mance"

    def test_espace_et_tiret(self):
        assert apply_case("SAINT-PIERRE DE LA ROCHE", "T-T:l:l:T") == "Saint-Pierre de la Roche"


class TestRegisterCasePattern:
    """register_fpe stocke case_pattern; lookup l'expose."""

    def test_register_et_lookup_case_pattern(self, tmp_path):
        reg = ScopeRegistry(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        reg.register_fpe(
            "patronyme",
            "Marc Leroy",
            surrogate="CHARVET",
            case_pattern=classify_case("Marc Leroy"),
        )
        record = reg.lookup("CHARVET")
        assert record is not None
        assert record.case_pattern == "T:T"
        reg.close()

    def test_register_sans_case_pattern_null(self, tmp_path):
        reg = ScopeRegistry(key=_KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        reg.register_fpe("siret", "73282932000033", surrogate="11111111111111")
        record = reg.lookup("11111111111111")
        assert record is not None
        assert record.case_pattern is None
        reg.close()


class TestMigrationV1V2:
    """Migration schema v1 -> v2: ALTER TABLE + entrées préservées."""

    def test_migration_v1_v2(self, tmp_path):
        path = str(tmp_path / "r.db")
        # Créer un registre v1 manuellement (schema v1 sans case_pattern)
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE meta (schema_version INTEGER NOT NULL, scope TEXT NOT NULL)")
        con.execute(
            "CREATE TABLE entries ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  surrogate TEXT NOT NULL,"
            "  entity_type TEXT NOT NULL,"
            "  clear_index INTEGER NOT NULL,"
            "  clear_hmac TEXT NOT NULL"
            ")"
        )
        con.execute("INSERT INTO meta(schema_version, scope) VALUES (1, 's')")
        con.execute(
            "INSERT INTO entries(surrogate, entity_type, clear_index, clear_hmac) "
            "VALUES ('OLDSUB', 'siret', 0, 'oldhmac')"
        )
        con.commit()
        con.close()

        # Ouvrir avec le code v2: migration doit s'appliquer
        reg = ScopeRegistry(key=_KEY, scope="s", registry_path=path)
        assert reg.schema_version() == CURRENT_SCHEMA_VERSION
        # L'ancienne entrée est préservée, case_pattern NULL
        record = reg.lookup("OLDSUB")
        assert record is not None
        assert record.entity_type == "siret"
        assert record.case_pattern is None
        # La nouvelle colonne existe et accepte un case_pattern
        reg.register_fpe(
            "patronyme",
            "Marc Leroy",
            surrogate="CHARVET",
            case_pattern="T:T",
        )
        record2 = reg.lookup("CHARVET")
        assert record2.case_pattern == "T:T"
        reg.close()

    def test_schema_version_actuel_est_4(self):
        assert CURRENT_SCHEMA_VERSION == 4


class TestFlagNonClair:
    """Le pattern casse ne contient pas le clair (invariant 1)."""

    def test_pattern_ne_contient_pas_clair(self):
        pattern = classify_case("Marc Leroy")
        assert "Marc" not in pattern
        assert "Leroy" not in pattern
        # Le pattern ne contient que U/l/T et ':'
        assert all(c in "UlT:" for c in pattern)
