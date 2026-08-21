"""Tests de la CLI anonyfy (phase 16).

Critères du PLAN phase 16 (10) + D11 (sécurité de la clé, registre persistant).
Référence: PLAN.md phase 16, DECISIONS.md D11/D4.

Convention: on appelle ``main(argv)`` directement (rapidité, argparse stdlib).
Le critère ``cross_process_roundtrip`` exige deux processus distincts: on
utilise ``subprocess`` + ``python -m anonyfy.cli``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from anonyfy.cli import _registry_path, main
from anonyfy.surrogate.registry import default_registry_path

# Clé de test hex: 32 hex chars = 16 octets nuls. Valeur nulle acceptable pour
# la logique métier (cf. tests existants key=b'0'*16); le round-trip FF3 est
# symétrique quelle que soit la clé.
KEY_HEX = "00" * 16


@pytest.fixture
def key_file_0600(tmp_path: Path) -> Path:
    """Fichier de clé en mode 0600 (propriétaire seul)."""
    p = tmp_path / "key.txt"
    p.write_text(KEY_HEX, encoding="utf-8")
    os.chmod(p, 0o600)
    return p


@pytest.fixture
def in_file(tmp_path: Path) -> Path:
    p = tmp_path / "in.txt"
    p.write_text("SIRET 73282932000033\n", encoding="utf-8")
    return p


class TestHelp:
    """Critère 2: --help affiche scan/mask/unmask."""

    def test_help_shows_subcommands(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "scan" in out
        assert "mask" in out
        assert "unmask" in out


class TestMaskEndToEnd:
    """Critère 3: mask end-to-end écrit un fichier non vide sans le clair."""

    def test_mask_writes_output_without_clear(self, tmp_path, in_file, monkeypatch, capsys):
        monkeypatch.setenv("ANONYFY_KEY", KEY_HEX)
        out = tmp_path / "out.txt"
        reg = tmp_path / "reg.db"
        rc = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--registry",
                str(reg),
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        assert out.exists() and out.stat().st_size > 0
        content = out.read_text(encoding="utf-8")
        assert "73282932000033" not in content


class TestKeyFilePermissions:
    """Critère 4 (D11): --key-file refuse mode groupe/autre (0644 → erreur)."""

    def test_refuse_group_readable_key_file(self, tmp_path, in_file, monkeypatch, capsys):
        kf = tmp_path / "key.txt"
        kf.write_text(KEY_HEX, encoding="utf-8")
        os.chmod(kf, 0o644)  # lisible par groupe/autre → refus
        monkeypatch.delenv("ANONYFY_KEY", raising=False)
        out = tmp_path / "out.txt"
        reg = tmp_path / "reg.db"
        rc = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--key-file",
                str(kf),
                "--registry",
                str(reg),
                "--out",
                str(out),
            ]
        )
        assert rc != 0
        assert not out.exists()
        err = capsys.readouterr().err
        assert "refus" in err.lower() or "mode" in err.lower() or "groupe" in err.lower()

    def test_accepts_0600_key_file(self, tmp_path, in_file, key_file_0600, monkeypatch):
        monkeypatch.delenv("ANONYFY_KEY", raising=False)
        out = tmp_path / "out.txt"
        reg = tmp_path / "reg.db"
        rc = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--key-file",
                str(key_file_0600),
                "--registry",
                str(reg),
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        assert out.exists() and out.stat().st_size > 0


class TestInheritedKeyWarning:
    """Critère 5 (D11): ANONYFY_KEY depuis l'env → avertissement affiché."""

    def test_warning_displayed_when_env_key_used(self, tmp_path, in_file, monkeypatch, capsys):
        monkeypatch.setenv("ANONYFY_KEY", KEY_HEX)
        out = tmp_path / "out.txt"
        reg = tmp_path / "reg.db"
        rc = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--registry",
                str(reg),
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        err = capsys.readouterr().err
        assert "avertissement" in err.lower()
        assert "anonyfy_key" in err.lower() or "héritée" in err.lower()

    def test_no_warning_when_key_file_used(
        self, tmp_path, in_file, key_file_0600, monkeypatch, capsys
    ):
        monkeypatch.delenv("ANONYFY_KEY", raising=False)
        out = tmp_path / "out.txt"
        reg = tmp_path / "reg.db"
        rc = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--key-file",
                str(key_file_0600),
                "--registry",
                str(reg),
                "--out",
                str(out),
            ]
        )
        assert rc == 0
        err = capsys.readouterr().err
        assert "avertissement" not in err.lower()


class TestKeyInClearRefused:
    """D11: --key en clair sur la ligne de commande est refusé (visible via ps)."""

    def test_refuses_key_argument(self, tmp_path, in_file, monkeypatch, capsys):
        monkeypatch.delenv("ANONYFY_KEY", raising=False)
        out = tmp_path / "out.txt"
        reg = tmp_path / "reg.db"
        rc = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--key",
                KEY_HEX,
                "--registry",
                str(reg),
                "--out",
                str(out),
            ]
        )
        assert rc != 0
        assert not out.exists()
        err = capsys.readouterr().err
        assert "refus" in err.lower() or "clé" in err.lower()


class TestScanDoesNotModifyInput:
    """Critère 8: scan produit un rapport sans modifier le fichier d'entrée."""

    def test_scan_does_not_modify_input(self, tmp_path, in_file, monkeypatch, capsys):
        monkeypatch.setenv("ANONYFY_KEY", KEY_HEX)
        reg = tmp_path / "reg.db"
        before = in_file.read_bytes()
        rc = main(["scan", str(in_file), "--scope", "s", "--registry", str(reg)])
        assert rc == 0
        after = in_file.read_bytes()
        assert before == after  # fichier d'entrée inchangé
        out = capsys.readouterr().out
        # Le rapport est produit (contient un titre/du contenu de rapport).
        assert "Rapport" in out or "rapport" in out.lower() or "SIRET" in out


class TestUnmaskEndToEnd:
    """Critère 7: unmask restitue le texte original (grep -q 73282932000033)."""

    def test_unmask_restores_original(self, tmp_path, in_file, key_file_0600, monkeypatch):
        monkeypatch.delenv("ANONYFY_KEY", raising=False)
        reg = tmp_path / "reg.db"
        masked = tmp_path / "masked.txt"
        restored = tmp_path / "restored.txt"
        # mask d'abord
        rc1 = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--key-file",
                str(key_file_0600),
                "--registry",
                str(reg),
                "--out",
                str(masked),
            ]
        )
        assert rc1 == 0
        assert "73282932000033" not in masked.read_text(encoding="utf-8")
        # unmask
        rc2 = main(
            [
                "unmask",
                str(masked),
                "--scope",
                "s",
                "--key-file",
                str(key_file_0600),
                "--registry",
                str(reg),
                "--out",
                str(restored),
            ]
        )
        assert rc2 == 0
        assert "73282932000033" in restored.read_text(encoding="utf-8")


class TestCrossProcessRoundtrip:
    """Critère 6 (D11): mask (proc 1) puis unmask (proc 2), même scope+registry."""

    def test_cross_process_roundtrip(self, tmp_path: Path):
        in_p = tmp_path / "in.txt"
        in_p.write_text("SIRET 73282932000033\n", encoding="utf-8")
        masked_p = tmp_path / "masked.txt"
        restored_p = tmp_path / "restored.txt"
        reg = tmp_path / "reg.db"
        kf = tmp_path / "key.txt"
        kf.write_text(KEY_HEX, encoding="utf-8")
        os.chmod(kf, 0o600)

        env_mask = dict(os.environ)
        env_mask["ANONYFY_KEY"] = KEY_HEX
        # Processus 1: mask via ANONYFY_KEY
        r1 = subprocess.run(
            [
                sys.executable,
                "-m",
                "anonyfy.cli",
                "mask",
                str(in_p),
                "--scope",
                "s",
                "--registry",
                str(reg),
                "--out",
                str(masked_p),
            ],
            env=env_mask,
            capture_output=True,
            text=True,
        )
        assert r1.returncode == 0, f"mask stderr: {r1.stderr}"
        assert masked_p.exists() and masked_p.stat().st_size > 0
        assert "73282932000033" not in masked_p.read_text(encoding="utf-8")

        # Processus 2: unmask via --key-file (pas d'ANONYFY_KEY)
        env_unmask = dict(os.environ)
        env_unmask.pop("ANONYFY_KEY", None)
        r2 = subprocess.run(
            [
                sys.executable,
                "-m",
                "anonyfy.cli",
                "unmask",
                str(masked_p),
                "--scope",
                "s",
                "--key-file",
                str(kf),
                "--registry",
                str(reg),
                "--out",
                str(restored_p),
            ],
            env=env_unmask,
            capture_output=True,
            text=True,
        )
        assert r2.returncode == 0, f"unmask stderr: {r2.stderr}"
        restored = restored_p.read_text(encoding="utf-8")
        assert "73282932000033" in restored


class TestDocsMenace:
    """Critère 9 (D11): docs/MENACE.md présent + contre-mesure/systemd/gestionnaire."""

    def test_docs_menace_present_with_countermeasures(self):
        p = Path("docs/MENACE.md")
        assert p.exists(), "docs/MENACE.md manquant"
        text = p.read_text(encoding="utf-8")
        assert "gestionnaire de secrets" in text or "systemd" in text or "contre-mesure" in text, (
            "MENACE.md doit mentionner gestionnaire de secrets, systemd ou contre-mesure"
        )


class TestKeyValidation:
    """D11: validation du format/longueur de la clé hex."""

    def test_invalid_hex_key_rejected(self, tmp_path, in_file, monkeypatch, capsys):
        monkeypatch.setenv("ANONYFY_KEY", "not-hex-zzzz")
        out = tmp_path / "out.txt"
        reg = tmp_path / "reg.db"
        rc = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--registry",
                str(reg),
                "--out",
                str(out),
            ]
        )
        assert rc != 0
        assert not out.exists()

    def test_wrong_length_key_rejected(self, tmp_path, in_file, monkeypatch, capsys):
        # 16 hex chars = 8 octets (trop court)
        monkeypatch.setenv("ANONYFY_KEY", "00" * 8)
        out = tmp_path / "out.txt"
        reg = tmp_path / "reg.db"
        rc = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--registry",
                str(reg),
                "--out",
                str(out),
            ]
        )
        assert rc != 0
        assert not out.exists()

    def test_no_key_rejected(self, tmp_path, in_file, monkeypatch, capsys):
        monkeypatch.delenv("ANONYFY_KEY", raising=False)
        out = tmp_path / "out.txt"
        reg = tmp_path / "reg.db"
        rc = main(
            [
                "mask",
                str(in_file),
                "--scope",
                "s",
                "--registry",
                str(reg),
                "--out",
                str(out),
            ]
        )
        assert rc != 0
        assert not out.exists()
        err = capsys.readouterr().err
        assert "clé" in err.lower()


class TestRegistryPathSanitization:
    """Phase 23 (Q2c): _registry_path sanitize le scope (path traversal).

    Sans sanitization, ``--scope "../../../tmp/evil"`` produit
    ``~/.anonyfy/registries/../../../tmp/evil.db`` = ``/tmp/evil.db``
    (path traversal via --scope). ``default_registry_path`` sanitize déjà;
    la CLI doit déléguer à cette fonction au lieu de recalculer le chemin.
    """

    def test_registry_path_sanitizes_traversal_scope(self):
        """Un scope malicieux ne produit pas un chemin hors du base."""
        args = type("Args", (), {"registry": None})()
        scope_malicieux = "../../../tmp/anonyfy_evil"
        chemin = _registry_path(args, scope_malicieux)
        base = os.path.realpath(os.path.expanduser("~/.anonyfy/registries"))
        real_chemin = os.path.realpath(chemin)
        assert real_chemin.startswith(base + os.sep), (
            f"chemin {real_chemin} hors du base {base} (path traversal non bloqué)"
        )
        assert "/tmp/" not in real_chemin

    def test_registry_path_equals_default_registry_path(self):
        """_registry_path délègue à default_registry_path (Q2b + Q2c)."""
        args = type("Args", (), {"registry": None})()
        for scope in ["default", "dossier-47", "../../../tmp/evil", "a/b/c"]:
            chemin = _registry_path(args, scope)
            attendu = default_registry_path(scope)
            assert chemin == attendu, (
                f"_registry_path({scope!r}) = {chemin!r} != default_registry_path = {attendu!r}"
            )

    def test_registry_path_explicit_registry_passthrough(self, tmp_path):
        """--registry explicite court-circuite le défaut (non-régression)."""
        explicit = str(tmp_path / "custom.db")
        args = type("Args", (), {"registry": explicit})()
        chemin = _registry_path(args, "nimporte")
        assert chemin == explicit

    def test_registry_path_calls_default_registry_path(self, monkeypatch):
        """Vérifie que _registry_path appelle default_registry_path (Q2b)."""
        called = {"ok": False}

        def fake(scope: str) -> str:
            called["ok"] = True
            return os.path.join("/fake", f"{scope}.db")

        import anonyfy.cli as cli_mod

        monkeypatch.setattr(cli_mod, "default_registry_path", fake)
        args = type("Args", (), {"registry": None})()
        _registry_path(args, "s")
        assert called["ok"], "default_registry_path n'a pas été appelée"
