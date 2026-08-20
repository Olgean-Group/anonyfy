"""API publique de masquage/démasquage anonyfy (phase 08).

``Vault`` orchestre le masquage (``mask``) et le démasquage (``unmask``) des
identifiants personnels structurés à grand domaine (D2: NIR, SIREN, SIRET, IBAN,
TVA, carte bancaire, téléphone).

- ``mask(text) -> MaskedText``: détecte les identifiants structurés, substitue par
  FPE (phase 07), enregistre chaque substitut dans le registre (phase 10), et
  substitue de droite à gauche (architecture §4). Le clair ne franchit jamais la
  frontière (invariant 1).
- ``unmask(text) -> str``: s'appuie sur l'automate Aho-Corasick (phase 10b) pour
  retrouver les substituts dans le texte (y compris reformatés), ne déchiffre que
  les substituts présents au registre (invariant 4), et restitue le clair par FPE
  ``decrypt_*``.

Référence: PLAN.md phase 08, invariants 1/2/3/4, architecture §4/§6.
"""

from __future__ import annotations

from anonyfy.resolve.aho_corasick import AhoCorasick
from anonyfy.surrogate.case_pattern import apply_case
from anonyfy.surrogate.engine import Engine
from anonyfy.surrogate.registry import ScopeRegistry
from anonyfy.types import EntityType, MaskedText

__all__ = ["Vault"]


class Vault:
    """API publique de pseudonymisation réversible des identifiants structurés.

    Args:
        key: clé FPE (16, 24 ou 32 bytes).
        scope: identifiant de scope (déterminisme scopé, invariant 2).
        registry_path: chemin du registre SQLite persistant.
        reference_patterns: patterns regex optionnels pour la référence de dossier
            (D2); ex. ``[r"DOS-\\d{6}"]``.
    """

    def __init__(
        self,
        *,
        key: bytes,
        scope: str,
        registry_path: str,
        reference_patterns: list[str] | None = None,
    ) -> None:
        self._key = key
        self._scope = scope
        self._registry = ScopeRegistry(key=key, scope=scope, registry_path=registry_path)
        self._engine = Engine(
            key=key, scope=scope, registry=self._registry,
            reference_patterns=reference_patterns,
        )

    def mask(self, text: str) -> MaskedText:
        """Masque les identifiants structurés de ``text``.

        Renvoie un ``MaskedText``: ``.text`` contient les substituts FPE (jamais
        le clair, invariant 1), ``.entities`` pointe vers les substituts réels.
        """
        return self._engine.mask(text)

    def unmask(self, text: str) -> str:
        """Restitue le texte clair à partir du texte masqué.

        S'appuie sur l'automate Aho-Corasick (phase 10b) pour retrouver les
        substituts dans le texte (y compris reformatés par le modèle), ne
        déchiffre que les substituts présents au registre (invariant 4), et
        restitue le clair par FPE ``decrypt_*``. Les substituts non reconnus au
        registre sont laissés tels quels (invariant 4: intrusion impossible).

        Le texte est normalisé (espaces entre chiffres supprimés) avant la
        recherche Aho-Corasick pour retrouver les substituts reformatés par le
        modèle (ex. SIRET groupé par 3, IBAN espacé). Les positions des hits sont
        remappées vers le texte original avant substitution.
        """
        normalized, offset_map = _normalize_inter_digit_spaces(text)

        ac = AhoCorasick.from_registry(self._registry)
        hits = ac.find(normalized)

        # Mapper les hits vers les positions du texte original et déchiffrer.
        replacements: list[tuple[int, int, str]] = []
        for hit in hits:
            if not self._registry.contains(hit.substitute):
                continue
            record = self._registry.lookup(hit.substitute)
            if record is None:
                continue
            etype = EntityType.coerce(record.entity_type)
            clear = self._engine.decrypt_surrogate(etype, hit.substitute)
            if clear is None:
                continue
            # D24: restituer la casse originale pour les types gazetteer.
            if record.case_pattern is not None:
                clear = apply_case(clear, record.case_pattern)
            orig_start = offset_map[hit.start]
            orig_end = offset_map[hit.end - 1] + 1
            replacements.append((orig_start, orig_end, clear))

        # Substitution de droite à gauche pour préserver les offsets.
        replacements.sort(key=lambda x: x[0], reverse=True)
        result = text
        for start, end, clear in replacements:
            result = result[:start] + clear + result[end:]
        return result

    def close(self) -> None:
        """Ferme le registre (commit + fermeture SQLite)."""
        self._registry.close()

    def __enter__(self) -> Vault:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _normalize_inter_digit_spaces(text: str) -> tuple[str, list[int]]:
    """Supprime les espaces entre chiffres et renvoie (normalisé, mapping).

    Le modèle peut reformater les substituts en groupant les chiffres par 3
    (ex. ``73282932000033`` -> ``732 829 320 000 33``). Cette normalisation
    supprime les espaces entourés de chiffres pour permettre à l'automate
    Aho-Corasick de retrouver le substitut compact.

    ``offset_map[i]`` donne la position dans le texte original du caractère
    ``normalisé[i]``, pour remapper les positions des hits vers le texte original.
    """
    normalized: list[str] = []
    offset_map: list[int] = []
    for i, ch in enumerate(text):
        if (
            ch == " "
            and normalized
            and normalized[-1].isdigit()
            and i + 1 < len(text)
            and text[i + 1].isdigit()
        ):
            # Espace entre deux chiffres: supprimer (reformatage du modèle).
            continue
        normalized.append(ch)
        offset_map.append(i)
    return "".join(normalized), offset_map
