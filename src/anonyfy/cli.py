"""Interface en ligne de commande anonyfy: scan / mask / unmask (phase 16).

CLI stdlib (``argparse``, zéro dépendance) conforme au PRD §4 et à D11
(sécurité de la clé) + D4 (registre persistant).

Sous-commandes:
  - ``scan <fichier>``: produit un rapport (``Vault.report()``) sans modifier
    le fichier d'entrée. Sortie sur stdout ou ``--out``.
  - ``scan FILE [FILE ...] --format json`` (phase 48): produit le contrat
    public ``anonyfy.report.v1`` en mode observation, agrégats uniquement.
  - ``mask <fichier> --scope <s> --out <out>``: masque les identifiants et
    écrit le résultat dans ``--out``.
  - ``unmask <fichier> --scope <s> --key-file <p> --out <out>``: restitue le
    texte clair à partir du fichier masqué.

Sécurité de la clé (D11, CRITIQUE):
  - ``--key`` en clair sur la ligne de commande est REFUSÉ (visible via ``ps``).
  - La clé provient de ``ANONYFY_KEY`` (env, hex) OU ``--key-file <path>``
    (fichier contenant la clé hex).
  - ``--key-file`` refuse un fichier lisible par groupe/autre (mode attendu:
    0600 ou 0400, propriétaire seul).
  - Un avertissement est affiché si la clé est héritée de ``ANONYFY_KEY``
    (peut fuiter vers les sous-processus).
  - La clé hex doit faire 32 hex chars (16 octets).

Mode JSON (phase 48): aucune clé n'est demandée ni acceptée. Une clé éphémère
(``secrets.token_bytes(16)``) et un registre dans un répertoire temporaire
supprimé en fin d'exécution garantissent qu'aucun état persistant n'est créé.
``--scope``, ``--registry`` et ``--audit`` sont refusés dans ce mode: ils
impliqueraient un état ou un journal persistants incompatibles avec un rapport
d'agrégats sans donnée source.

Le registre est persistant entre invocations (D11/D4): ``--registry <path>``
ou défaut ``~/.anonyfy/registries/<scope>.db``. Le clair n'est jamais loggé ni
affiché (invariant 1); le registre ne stocke jamais de clair (D4).

Référence: PLAN.md phase 16, DECISIONS.md D11/D4, phase 48 (contrat public).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from anonyfy import __version__
from anonyfy.audit import AuditLog
from anonyfy.detect.gazetteers.loader import gazetteer_version
from anonyfy.observation_report import ObservationReportBuilder
from anonyfy.surrogate.registry import default_registry_path
from anonyfy.vault import WEAK_CONFIDENCE_THRESHOLD, Vault

__all__ = ["build_parser", "main"]

# Bornes du contrat public v1 (schéma normatif anonyfy.report.v1).
MAX_DOCUMENTS = 50
# Scope interne fixe du scan JSON: jamais exposé, jamais persisté.
_JSON_SCOPE = "scan-observation"


def _parse_hex_key(hex_str: str, err_stream: IO[str]) -> bytes | None:
    """Valide et décode une clé hex (32 hex chars = 16 octets).

    Retourne la clé en bytes, ou ``None`` si invalide (message sur err_stream).
    """
    try:
        key = bytes.fromhex(hex_str)
    except ValueError:
        print("erreur: clé hex invalide (caractères non hexadécimaux)", file=err_stream)
        return None
    if len(key) != 16:
        print(
            f"erreur: la clé doit faire 16 octets (32 hex chars), reçu {len(key)} octets",
            file=err_stream,
        )
        return None
    return key


def _resolve_key(args: argparse.Namespace, err_stream: IO[str]) -> bytes | None:
    """Résout la clé depuis ``--key-file`` ou ``ANONYFY_KEY``, avec les gardes D11.

    Ordre de priorité:
      1. ``--key`` en clair → REFUS (visible via ps).
      2. ``--key-file`` → lecture + vérification du mode (refus groupe/autre).
      3. ``ANONYFY_KEY`` (env) → avertissement (héritée par les sous-processus).

    Retourne la clé en bytes, ou ``None`` si invalide/refusée (message sur
    err_stream). La clé n'est jamais affichée en clair (invariant 1).
    """
    # 1. --key en clair: refusé (visible via ps).
    if getattr(args, "key", None) is not None:
        print(
            "refus: --key en clair sur la ligne de commande est interdit "
            "(visible via ps); utilisez ANONYFY_KEY (env) ou --key-file",
            file=err_stream,
        )
        return None

    # 2. --key-file: vérifie le mode (refuse groupe/autre).
    key_file = getattr(args, "key_file", None)
    if key_file is not None:
        path = Path(key_file)
        try:
            st = path.stat()
        except OSError as exc:
            print(f"erreur: fichier de clé introuvable: {exc}", file=err_stream)
            return None
        mode = st.st_mode
        if mode & 0o077:
            print(
                f"refus: le fichier de clé {path} est lisible par groupe/autre "
                f"(mode {oct(mode & 0o777)}); attendu 0600 ou 0400 (propriétaire seul)",
                file=err_stream,
            )
            return None
        hex_str = path.read_text(encoding="utf-8").strip()
        return _parse_hex_key(hex_str, err_stream)

    # 3. ANONYFY_KEY (env): avertissement (héritée par les sous-processus).
    env_key = os.environ.get("ANONYFY_KEY")
    if env_key:
        print(
            "avertissement: la clé ANONYFY_KEY héritée de l'environnement peut "
            "fuiter vers les sous-processus; préférez --key-file",
            file=err_stream,
        )
        return _parse_hex_key(env_key.strip(), err_stream)

    print(
        "erreur: aucune clé fournie; utilisez ANONYFY_KEY (env) ou --key-file",
        file=err_stream,
    )
    return None


def _registry_path(args: argparse.Namespace, scope: str) -> str:
    """Retourne le chemin du registre: ``--registry`` ou défaut explicite.

    Défaut D4/D11: ``~/.anonyfy/registries/<scope>.db``. Le défaut est calculé
    par ``default_registry_path`` qui sanitize le scope (remplace tout
    caractère non alnum/-/_/. par ``_``), bloquant le path traversal via
    ``--scope`` (phase 23, Q2c). Le répertoire parent est créé par
    ``ScopeRegistry.__init__`` (registry.py), pas besoin de le faire ici.
    """
    if getattr(args, "registry", None):
        return args.registry
    return default_registry_path(scope)


def _read_input(path: str, err_stream: IO[str]) -> str | None:
    """Lit le fichier d'entrée en UTF-8. Retourne ``None`` si erreur."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"erreur: lecture du fichier d'entrée échouée: {exc}", file=err_stream)
        return None


def _cmd_scan(args: argparse.Namespace, out_stream: IO[str], err_stream: IO[str]) -> int:
    """scan: produit un rapport sans modifier les fichiers d'entrée.

    Deux formats (phase 48):
      - ``markdown`` (défaut, historique): ``Vault.report()`` pour UN fichier,
        clé requise (D11), registre persistant selon ``--registry``/``--scope``.
      - ``json``: contrat public ``anonyfy.report.v1`` pour 1 à 50 fichiers,
        mode observation, clé éphémère, aucun état persistant.

    Le fichier d'entrée est seulement lu. Le masquage effectué en mémoire pour
    peupler les compteurs du rapport (PRD F10) n'écrit ni texte masqué ni
    registre pour le format JSON.
    """
    if args.format == "json":
        return _cmd_scan_json(args, out_stream, err_stream)
    return _cmd_scan_markdown(args, out_stream, err_stream)


def _cmd_scan_markdown(args: argparse.Namespace, out_stream: IO[str], err_stream: IO[str]) -> int:
    """scan Markdown historique (mono-fichier, clé requise)."""
    if len(args.fichier) != 1:
        print(
            "erreur: le format markdown accepte un seul fichier; "
            "utilisez --format json pour un corpus",
            file=err_stream,
        )
        return 1
    key = _resolve_key(args, err_stream)
    if key is None:
        return 1
    text = _read_input(args.fichier[0], err_stream)
    if text is None:
        return 1
    reg = _registry_path(args, args.scope)
    audit = AuditLog(args.audit) if getattr(args, "audit", None) else None
    vault = Vault(key=key, scope=args.scope, registry_path=reg, audit=audit)
    try:
        vault.mask(text)  # peuple les compteurs; le masqué n'est pas persisté.
        report = vault.report()
    finally:
        vault.close()
    out_path = getattr(args, "out", None)
    if out_path:
        Path(out_path).write_text(report, encoding="utf-8")
    else:
        out_stream.write(report)
        if not report.endswith("\n"):
            out_stream.write("\n")
    return 0


def _reject_json_persistent_options(args: argparse.Namespace, err_stream: IO[str]) -> bool:
    """Refuse les options incompatibles avec un scan JSON sans état.

    ``--registry``, ``--scope`` (explicite) et ``--audit`` impliqueraient un
    état ou un journal persistants. Le mode observation n'en veut aucun: la
    détection ne substitue rien et le rapport ne porte que des agrégats.

    Retourne ``True`` si une option a été refusée (déjà signalée).
    """
    registry = getattr(args, "registry", None)
    if registry:
        print(
            "refus: --registry est interdit avec --format json "
            "(le scan observation ne crée aucun registre persistant)",
            file=err_stream,
        )
        return True
    if getattr(args, "scope", None) != "default":
        print(
            "refus: --scope est interdit avec --format json "
            "(le scan observation ne persiste aucun scope)",
            file=err_stream,
        )
        return True
    if getattr(args, "audit", None):
        print(
            "refus: --audit est interdit avec --format json "
            "(aucun journal de traces de source n'est écrit en observation)",
            file=err_stream,
        )
        return True
    if getattr(args, "key_file", None):
        print(
            "refus: --key-file est interdit avec --format json "
            "(le scan observation utilise une clé éphémère non exportée)",
            file=err_stream,
        )
        return True
    if getattr(args, "key", None):
        print(
            "refus: --key est interdit avec --format json "
            "(le scan observation utilise une clé éphémère non exportée)",
            file=err_stream,
        )
        return True
    return False


def _cmd_scan_json(args: argparse.Namespace, out_stream: IO[str], err_stream: IO[str]) -> int:
    """scan JSON: contrat public ``anonyfy.report.v1`` en mode observation.

    Aucune clé n'est lue (ni ``ANONYFY_KEY``, ni ``--key-file``): la clé est
    éphémère et sert uniquement à instancier le Vault, puisque l'observation ne
    substitue rien. Le registre vit dans un répertoire temporaire supprimé en
    fin d'exécution; aucun ``.db`` ne survit à la commande.
    """
    if _reject_json_persistent_options(args, err_stream):
        return 1
    paths = args.fichier
    if len(paths) > MAX_DOCUMENTS:
        print(
            f"erreur: {len(paths)} fichiers fournis; le contrat v1 accepte au plus "
            f"{MAX_DOCUMENTS} documents",
            file=err_stream,
        )
        return 1

    builder = ObservationReportBuilder(confidence_threshold=WEAK_CONFIDENCE_THRESHOLD)
    with tempfile.TemporaryDirectory(prefix="anonyfy-observation-") as workdir:
        vault = Vault(
            key=secrets.token_bytes(16),
            scope=_JSON_SCOPE,
            registry_path=str(Path(workdir) / "registry.db"),
        )
        try:
            for raw_path in paths:
                path = Path(raw_path)
                try:
                    text = path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    print(
                        f"erreur: fichier non décodable en UTF-8: {path}",
                        file=err_stream,
                    )
                    return 1
                except OSError as exc:
                    print(f"erreur: lecture du fichier d'entrée échouée: {exc}", file=err_stream)
                    return 1
                result = vault.mask(text, observe=True)
                # Seuls la taille et les spans sont transmis: ni texte, ni chemin.
                builder.add_document(character_count=len(text), spans=result.entities)
        finally:
            vault.close()

    report = builder.build(
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        producer_version=__version__,
        gazetteer_version=gazetteer_version(),
    )
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    out_path = getattr(args, "out", None)
    if out_path:
        try:
            Path(out_path).write_text(payload, encoding="utf-8")
        except OSError as exc:
            print(f"erreur: écriture du rapport échouée: {exc}", file=err_stream)
            return 1
    else:
        out_stream.write(payload)
    return 0


def _cmd_mask(args: argparse.Namespace, out_stream: IO[str], err_stream: IO[str]) -> int:
    """mask: masque les identifiants et écrit le résultat dans ``--out``."""
    key = _resolve_key(args, err_stream)
    if key is None:
        return 1
    text = _read_input(args.fichier, err_stream)
    if text is None:
        return 1
    reg = _registry_path(args, args.scope)
    audit = AuditLog(args.audit) if getattr(args, "audit", None) else None
    vault = Vault(key=key, scope=args.scope, registry_path=reg, audit=audit)
    try:
        masked = vault.mask(text)
    finally:
        vault.close()
    Path(args.out).write_text(masked.text, encoding="utf-8")
    return 0


def _cmd_unmask(args: argparse.Namespace, out_stream: IO[str], err_stream: IO[str]) -> int:
    """unmask: restitue le texte clair à partir du fichier masqué."""
    key = _resolve_key(args, err_stream)
    if key is None:
        return 1
    text = _read_input(args.fichier, err_stream)
    if text is None:
        return 1
    reg = _registry_path(args, args.scope)
    vault = Vault(key=key, scope=args.scope, registry_path=reg)
    try:
        restored = vault.unmask(text)
    finally:
        vault.close()
    Path(args.out).write_text(restored, encoding="utf-8")
    return 0


def _add_key_arguments(parser: argparse.ArgumentParser) -> None:
    """Ajoute les arguments de clé communs (D11).

    ``--key`` est défini pour pouvoir le refuser explicitement avec un message
    clair (sinon argparse dirait juste « unrecognized arguments »).
    """
    parser.add_argument("--key-file", help="fichier contenant la clé hex (mode 0600)")
    parser.add_argument(
        "--key",
        help="REFUSÉ: clé en clair interdite (visible via ps); utilisez ANONYFY_KEY ou --key-file",
    )


def build_parser() -> argparse.ArgumentParser:
    """Construit le parseur argparse de la CLI anonyfy."""
    parser = argparse.ArgumentParser(
        prog="anonyfy",
        description="Anonymisation réversible par pseudonymisation (scan / mask / unmask).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # scan
    sp_scan = sub.add_parser(
        "scan",
        help="produit un rapport sans modifier le fichier d'entrée",
    )
    sp_scan.add_argument(
        "fichier",
        nargs="+",
        help="fichier(s) à scanner (1 à 50 en --format json)",
    )
    sp_scan.add_argument("--scope", default="default", help="identifiant de scope")
    sp_scan.add_argument("--registry", help="chemin du registre SQLite")
    sp_scan.add_argument("--out", help="fichier de sortie du rapport (défaut: stdout)")
    sp_scan.add_argument("--audit", help="chemin du journal d'audit (optionnel)")
    sp_scan.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="format du rapport: markdown (défaut, mono-fichier) ou json (contrat v1)",
    )
    _add_key_arguments(sp_scan)
    sp_scan.set_defaults(func=_cmd_scan)

    # mask
    sp_mask = sub.add_parser(
        "mask",
        help="masque les identifiants et écrit le résultat dans --out",
    )
    sp_mask.add_argument("fichier", help="fichier à masquer")
    sp_mask.add_argument("--scope", required=True, help="identifiant de scope")
    sp_mask.add_argument("--registry", help="chemin du registre SQLite")
    sp_mask.add_argument("--out", required=True, help="fichier de sortie masqué")
    sp_mask.add_argument("--audit", help="chemin du journal d'audit (optionnel)")
    _add_key_arguments(sp_mask)
    sp_mask.set_defaults(func=_cmd_mask)

    # unmask
    sp_unmask = sub.add_parser(
        "unmask",
        help="restitue le texte clair à partir d'un fichier masqué",
    )
    sp_unmask.add_argument("fichier", help="fichier masqué à démasquer")
    sp_unmask.add_argument("--scope", required=True, help="identifiant de scope")
    sp_unmask.add_argument("--registry", help="chemin du registre SQLite")
    sp_unmask.add_argument("--out", required=True, help="fichier de sortie démasqué")
    _add_key_arguments(sp_unmask)
    sp_unmask.set_defaults(func=_cmd_unmask)

    return parser


def main(
    argv: list[str] | None = None,
    out: IO[str] | None = None,
    err: IO[str] | None = None,
) -> int:
    """Point d'entrée de la CLI anonyfy.

    Args:
        argv: liste d'arguments (défaut: ``sys.argv[1:]``).
        out: flux de sortie (défaut: ``sys.stdout``).
        err: flux d'erreur (défaut: ``sys.stderr``).

    Retourne un code de sortie (0 = succès, non-zero = erreur). Les erreurs
    argparse (arguments manquants/invalides) lèvent ``SystemExit`` (comportement
    standard argparse).
    """
    out_stream = out if out is not None else sys.stdout
    err_stream = err if err is not None else sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args, out_stream, err_stream)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
