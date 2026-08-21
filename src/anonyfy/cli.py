"""Interface en ligne de commande anonyfy: scan / mask / unmask (phase 16).

CLI stdlib (``argparse``, zéro dépendance) conforme au PRD §4 et à D11
(sécurité de la clé) + D4 (registre persistant).

Sous-commandes:
  - ``scan <fichier>``: produit un rapport (``Vault.report()``) sans modifier
    le fichier d'entrée. Sortie sur stdout ou ``--out``.
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

Le registre est persistant entre invocations (D11/D4): ``--registry <path>``
ou défaut ``~/.anonyfy/registries/<scope>.db``. Le clair n'est jamais loggé ni
affiché (invariant 1); le registre ne stocke jamais de clair (D4).

Référence: PLAN.md phase 16, DECISIONS.md D11/D4.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import IO

from anonyfy.audit import AuditLog
from anonyfy.surrogate.registry import default_registry_path
from anonyfy.vault import Vault

__all__ = ["build_parser", "main"]


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
    """scan: produit un rapport (Vault.report()) sans modifier le fichier d'entrée.

    Le fichier d'entrée est seulement lu. Le rapport est écrit sur stdout ou
    dans ``--out``. Le masquage est effectué en mémoire pour peupler les
    compteurs du rapport (PRD F10); le texte masqué n'est pas écrit.
    """
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
    sp_scan.add_argument("fichier", help="fichier à scanner")
    sp_scan.add_argument("--scope", default="default", help="identifiant de scope")
    sp_scan.add_argument("--registry", help="chemin du registre SQLite")
    sp_scan.add_argument("--out", help="fichier de sortie du rapport (défaut: stdout)")
    sp_scan.add_argument("--audit", help="chemin du journal d'audit (optionnel)")
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
