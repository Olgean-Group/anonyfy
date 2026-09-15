"""Scan JSON multi-fichiers agrégat-seul (phase 48, PRD F7/F10, plan Task 3).

``anonyfy scan FILE [FILE ...] --format json --out report.json`` produit le
contrat ``anonyfy.report.v1`` en mode observation: clé éphémère, registre dans
un répertoire temporaire supprimé, aucune valeur source ni nom de fichier dans
la sortie. Le format par défaut reste ``markdown`` (rétrocompatibilité du scan
mono-fichier).

Référence: ``docs/superpowers/plans/01-anonyfy-public-report-contract.md``
(phase 48, Task 3).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from anonyfy.cli import main
from anonyfy.schemas import load_report_schema

SIRET = "73282932000033"


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch):
    """Le mode JSON ne doit exiger aucune clé: on retire l'environnement."""
    monkeypatch.delenv("ANONYFY_KEY", raising=False)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_scan_json_multi_file_emits_safe_aggregates(tmp_path):
    text1 = f"SIRET {SIRET}\n"
    text2 = "RAS\n"
    file1 = _write(tmp_path / "dossier-a.txt", text1)
    file2 = _write(tmp_path / "dossier-b.txt", text2)
    output = tmp_path / "report.json"

    rc = main(["scan", str(file1), str(file2), "--format", "json", "--out", str(output)])

    assert rc == 0
    raw = output.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["schema_version"] == "1.0"
    assert data["producer"]["name"] == "anonyfy"
    assert data["observation"]["mode"] == "observation"
    assert data["observation"]["document_count"] == 2
    assert data["observation"]["character_count"] == len(text1) + len(text2)
    assert data["observation"]["total_occurrence_count"] >= 1
    assert SIRET not in raw
    assert file1.name not in raw
    assert file2.name not in raw


def test_scan_json_output_matches_normative_schema(tmp_path):
    file1 = _write(tmp_path / "a.txt", f"SIRET {SIRET}\n")
    file2 = _write(tmp_path / "b.txt", "M. Jean Dupont\n")
    output = tmp_path / "report.json"

    rc = main(["scan", str(file1), str(file2), "--format", "json", "--out", str(output)])

    assert rc == 0
    Draft202012Validator(load_report_schema()).validate(
        json.loads(output.read_text(encoding="utf-8"))
    )


def test_scan_json_accepts_exactly_fifty_documents(tmp_path):
    files = [_write(tmp_path / f"doc-{index:03d}.txt", f"SIRET {SIRET}\n") for index in range(50)]
    output = tmp_path / "report.json"

    rc = main(["scan", *(str(path) for path in files), "--format", "json", "--out", str(output)])

    assert rc == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["observation"]["document_count"] == 50
    Draft202012Validator(load_report_schema()).validate(data)


def test_scan_json_writes_to_stdout_without_out(tmp_path):
    file1 = _write(tmp_path / "a.txt", f"SIRET {SIRET}\n")
    out_stream = io.StringIO()

    rc = main(["scan", str(file1), "--format", "json"], out=out_stream, err=io.StringIO())

    assert rc == 0
    data = json.loads(out_stream.getvalue())
    assert data["observation"]["document_count"] == 1
    assert SIRET not in out_stream.getvalue()


def test_scan_json_creates_no_persistent_registry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    file1 = _write(tmp_path / "a.txt", f"SIRET {SIRET}\n")

    rc = main(
        ["scan", str(file1), "--format", "json", "--out", str(tmp_path / "report.json")],
        err=io.StringIO(),
    )

    assert rc == 0
    assert list(tmp_path.glob("**/*.db")) == []
    assert not (Path.home() / ".anonyfy" / "registries" / "scan-observation.db").exists()


def test_default_format_is_still_markdown(tmp_path):
    file1 = _write(tmp_path / "a.txt", f"SIRET {SIRET}\n")
    out_stream = io.StringIO()

    rc = main(["scan", str(file1)], out=out_stream, err=io.StringIO())

    assert rc != 0  # markdown exige une clé (comportement historique)
    assert "Rapport" not in out_stream.getvalue()


def test_scan_markdown_single_file_still_works_with_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANONYFY_KEY", "00" * 16)
    file1 = _write(tmp_path / "a.txt", f"SIRET {SIRET}\n")
    out_stream = io.StringIO()

    rc = main(
        ["scan", str(file1), "--scope", "s", "--registry", str(tmp_path / "reg.db")],
        out=out_stream,
        err=io.StringIO(),
    )

    assert rc == 0
    assert "Rapport" in out_stream.getvalue()


def test_scan_json_rejects_key_or_registry_options(tmp_path):
    file1 = _write(tmp_path / "a.txt", f"SIRET {SIRET}\n")
    output = tmp_path / "report.json"
    err_stream = io.StringIO()

    rc = main(
        [
            "scan",
            str(file1),
            "--format",
            "json",
            "--registry",
            str(tmp_path / "reg.db"),
            "--out",
            str(output),
        ],
        err=err_stream,
    )

    assert rc != 0
    assert not output.exists()
    assert "--registry" in err_stream.getvalue()


def test_scan_json_rejects_audit_journal(tmp_path):
    file1 = _write(tmp_path / "a.txt", f"SIRET {SIRET}\n")
    output = tmp_path / "report.json"
    err_stream = io.StringIO()

    rc = main(
        [
            "scan",
            str(file1),
            "--format",
            "json",
            "--audit",
            str(tmp_path / "audit.jsonl"),
            "--out",
            str(output),
        ],
        err=err_stream,
    )

    assert rc != 0
    assert not output.exists()
    assert not (tmp_path / "audit.jsonl").exists()
    assert "--audit" in err_stream.getvalue()


def test_scan_json_rejects_key_options(tmp_path):
    file1 = _write(tmp_path / "a.txt", f"SIRET {SIRET}\n")
    key_file = tmp_path / "key.txt"
    key_file.write_text("00" * 16, encoding="utf-8")
    key_file.chmod(0o600)
    output = tmp_path / "report.json"
    err_stream = io.StringIO()

    rc = main(
        [
            "scan",
            str(file1),
            "--format",
            "json",
            "--key-file",
            str(key_file),
            "--out",
            str(output),
        ],
        err=err_stream,
    )

    assert rc != 0
    assert not output.exists()
    assert "--key-file" in err_stream.getvalue()


def test_scan_json_rejects_more_than_fifty_paths(tmp_path):
    files = [_write(tmp_path / f"doc-{index:03d}.txt", "RAS\n") for index in range(51)]
    output = tmp_path / "report.json"

    rc = main(
        ["scan", *(str(path) for path in files), "--format", "json", "--out", str(output)],
        err=io.StringIO(),
    )

    assert rc != 0
    assert not output.exists()


def test_scan_json_rejects_unreadable_file(tmp_path):
    missing = tmp_path / "absent.txt"
    output = tmp_path / "report.json"

    rc = main(["scan", str(missing), "--format", "json", "--out", str(output)], err=io.StringIO())

    assert rc != 0
    assert not output.exists()


def test_scan_json_rejects_invalid_utf8_without_output(tmp_path):
    bad = tmp_path / "binaire.txt"
    bad.write_bytes(b"\xff\xfe\x00\x01")
    output = tmp_path / "report.json"
    err_stream = io.StringIO()

    rc = main(["scan", str(bad), "--format", "json", "--out", str(output)], err=err_stream)

    assert rc != 0
    assert not output.exists()
    assert "UTF-8" in err_stream.getvalue() or "encodage" in err_stream.getvalue()


def test_scan_json_rejects_document_larger_than_contract_bound(tmp_path):
    huge = tmp_path / "huge.txt"
    huge.write_text("a" * (50_000_000 + 1), encoding="utf-8")
    output = tmp_path / "report.json"
    err_stream = io.StringIO()

    rc = main(["scan", str(huge), "--format", "json", "--out", str(output)], err=err_stream)

    assert rc != 0
    assert not output.exists()
    assert "50" in err_stream.getvalue()


def test_scan_json_reports_output_write_failure(tmp_path):
    file1 = _write(tmp_path / "a.txt", f"SIRET {SIRET}\n")
    output = tmp_path / "report.json"
    output.mkdir()

    rc = main(["scan", str(file1), "--format", "json", "--out", str(output)], err=io.StringIO())

    assert rc != 0
    assert output.is_dir()
    assert output.is_dir() and not any(output.iterdir())
