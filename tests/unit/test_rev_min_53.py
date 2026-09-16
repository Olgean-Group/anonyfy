"""Phase 53 — REV-MIN-3/5/6/9 : dettes mineures de la revue S8.

- REV-MIN-3 (OBJ-002 résidu) : aucun test ne verrouillait le point fixe
  CODE_POSTAL sur le chemin couplé (commune + CP). Cas réel trouvé :
  « habite à 68220 Abergement-Clémenciat » où le CP de la commune substituée
  (Michelbach-le-Haut, 68220) égale le CP clair. Le sondage doit sauter le
  point fixe et le filet global garantir l'absence de fuite.
- REV-MIN-5 (OBJ-108) : les canaris de version (`test_smoke`, `test_package`)
  codaient « 0.1.7 » en dur ; ils doivent lire `pyproject.toml` pour que le
  prochain bump ne les oublie pas.
- REV-MIN-6 : `ff3` n'a pas de borne supérieure ; un majeur 2.x casserait la
  compatibilité des registres persistés (invariant 2) sans que rien ne le
  signale.
- REV-MIN-9 (OBJ-107) : le seuil de latence dense (100 ms) est proche des
  mesures CI et peut flaker ; le test doit tolérer la variance machine sans
  devenir tautologique (médiane de plusieurs runs plutôt que meilleur cas).

Référence: ``.olgenius/REVUE-CODE.html`` (S8.2), BACKLOG REV-MIN-3/5/6/9.
"""

from __future__ import annotations

import re
import statistics
import time
import tomllib
from pathlib import Path

from anonyfy import Vault
from anonyfy.types import EntityType

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
KEY = b"0" * 16


class TestCPPointFixe:
    """REV-MIN-3 : le point fixe CP (chemin couplé) est sauté et sans fuite."""

    #: Cas réel: le CP de la commune substituée est identique au CP clair.
    CAS = "habite à 68220 Abergement-Clémenciat"

    def test_point_fixe_saute_et_round_trip(self, tmp_path):
        v = Vault(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        try:
            m = v.mask(self.CAS)
            assert "68220" not in m.text, (
                f"fuite invariant 1: le CP point fixe reste en clair dans {m.text!r}"
            )
            cp_spans = [s for s in m.entities if s.type == EntityType.CODE_POSTAL]
            assert len(cp_spans) == 1
            assert re.fullmatch(r"\d{5}", cp_spans[0].value)
            assert cp_spans[0].value != "68220", "le substitut CP ne doit pas être le point fixe"
            assert v.unmask(m.text) == self.CAS, "round-trip échoué sur le point fixe CP"
        finally:
            v.close()

    def test_point_fixe_cp_du_departement_cible_est_detecte(self, tmp_path):
        """La condition de point fixe est reproductible: le CP de la commune
        substituée égale le CP clair. Ce test documente le cas (contrôle)."""
        from anonyfy.detect.gazetteers.loader import load_codes_postaux, load_communes
        from anonyfy.surrogate.gazetteer_cipher import GazetteerCipher

        gaz = load_communes()
        cipher = GazetteerCipher(KEY, "s", "commune", gaz)
        substitute = cipher.encrypt("Abergement-Clémenciat")
        entry = gaz[substitute.casefold()]
        cp_sub = load_codes_postaux().get(entry.code_commune)
        assert cp_sub == "68220", (
            f"cas de point fixe modifié: CP substitut {cp_sub!r} != 68220 "
            "(le gazetteer ou la clé ont changé)"
        )


class TestCanarisParametriques:
    """REV-MIN-5 : les canaris de version lisent pyproject.toml."""

    def test_smoke_uses_pyproject_version(self):
        text = (REPO / "tests" / "unit" / "test_smoke.py").read_text(encoding="utf-8")
        assert "tomllib" in text, "test_smoke doit lire pyproject.toml (tomllib)"
        assert "0.1.7" not in text, "test_smoke ne doit plus coder la version en dur (OBJ-108)"

    def test_package_uses_pyproject_version(self):
        text = (REPO / "tests" / "unit" / "test_package.py").read_text(encoding="utf-8")
        assert "tomllib" in text, "test_package doit lire pyproject.toml (tomllib)"
        assert "0.1.7" not in text, "test_package ne doit plus coder la version en dur (OBJ-108)"

    def test_version_module_still_pins_expected_version(self):
        """test_version reste le point d'ancrage explicite du bump."""
        text = (REPO / "tests" / "unit" / "test_version.py").read_text(encoding="utf-8")
        with PYPROJECT.open("rb") as fh:
            current = tomllib.load(fh)["project"]["version"]
        assert current in text, (
            f"test_version doit indiquer la version courante ({current}) du bump"
        )


class TestFF3Borne:
    """REV-MIN-6 : ff3 porte une borne supérieure (<2)."""

    def test_ff3_has_upper_bound(self):
        with PYPROJECT.open("rb") as fh:
            project = tomllib.load(fh)["project"]
        ff3_specs = [dep for dep in project["dependencies"] if dep.startswith("ff3")]
        assert ff3_specs == ["ff3>=1.0.3,<2"], (
            f"ff3 doit porter une borne supérieure <2 (invariant 2), reçu {ff3_specs!r}"
        )

    def test_ff3_installed_is_1x(self):
        import importlib.metadata as md

        version = md.version("ff3")
        major = int(version.split(".")[0])
        assert major == 1, f"ff3 installé en {version} (majeur 2 non supporté)"


class TestFF3Snapshot:
    """REV-MIN-6 : snapshot de rétro-compatibilité des substituts FPE persistés.

    Les substituts FPE dérivent de la clé, du scope, du type et de la
    bibliothèque ``ff3``. Un changement de version majeure (ou une régression
    silencieuse) casserait la réversibilité des registres déjà persistés
    (invariant 2) sans qu'aucun test ne le signale. Ce snapshot fige les
    substituts d'un corpus synthétique pour la clé de test connue.
    """

    #: (clair, substituts attendus) — généré sur ff3 1.0.3, clé nulle, scope snapshot-ff3.
    SNAPSHOT = (
        ("SIRET 73282932000033", [("SIRET", "55061068501994")]),
        ("SIREN 732829320", [("SIREN", "617736749")]),
        ("NIR 275032917028004", [("NIR", "204371869589188")]),
        (
            "IBAN FR7630006000011234567890189",
            [("IBAN", "FR7747839640540707616378956")],
        ),
        ("CB 4970100000000055", [("CARTE_BANCAIRE", "0591132510571389")]),
        ("TEL 0612345678", [("PATRONYME", "MAPP"), ("TELEPHONE", "0694957359")]),
        ("PLAQUE AB-123-CD", [("PLAQUE_SIV", "AB-467-CD")]),
    )

    def test_fpe_substitutes_match_snapshot(self, tmp_path):
        v = Vault(key=KEY, scope="snapshot-ff3", registry_path=str(tmp_path / "r.db"))
        try:
            for text, expected in self.SNAPSHOT:
                m = v.mask(text)
                got = [(s.type.value, s.value) for s in m.entities]
                assert got == expected, (
                    f"substituts modifiés pour {text!r}: {got!r} != {expected!r} "
                    "(régression de rétro-compatibilité des registres, invariant 2)"
                )
        finally:
            v.close()

    def test_snapshot_round_trips(self, tmp_path):
        v = Vault(key=KEY, scope="snapshot-ff3", registry_path=str(tmp_path / "r.db"))
        try:
            for text, _expected in self.SNAPSHOT:
                assert v.unmask(v.mask(text).text) == text, f"round-trip échoué: {text!r}"
        finally:
            v.close()


class TestFlakinessLatence:
    """REV-MIN-9 : le test dense utilise une statistique robuste, pas le meilleur cas."""

    def test_latency_test_uses_median_not_best(self):
        text = (REPO / "tests" / "acceptance" / "test_latency.py").read_text(encoding="utf-8")
        assert "median" in text, (
            "test_latency doit utiliser une statistique robuste (median) pour le cas dense"
        )

    def test_dense_mask_stays_under_robust_threshold(self, tmp_path):
        """Le seuil robuste (médiane) reste sous 100 ms sur cette machine."""
        from tests.acceptance.test_latency import _DENSE_TEXT, _RUNS

        v = Vault(key=KEY, scope="s", registry_path=str(tmp_path / "r.db"))
        try:
            v.mask(_DENSE_TEXT)  # échauffement
            samples = []
            for _ in range(_RUNS):
                start = time.perf_counter()
                v.mask(_DENSE_TEXT)
                samples.append((time.perf_counter() - start) * 1000.0)
            median = statistics.median(samples)
            assert median < 100.0, f"latence médiane {median:.2f} ms >= 100 ms"
        finally:
            v.close()
