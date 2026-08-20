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
from anonyfy.surrogate.engine import _TYPES, Engine
from anonyfy.surrogate.registry import ScopeRegistry
from anonyfy.types import EntityType, MaskedText

__all__ = ["Vault"]


class Vault:
    """API publique de pseudonymisation réversible des identifiants structurés.

    Args:
        key: clé FPE (16, 24 ou 32 bytes).
        scope: identifiant de scope (déterminisme scopé, invariant 2).
        registry_path: chemin du registre SQLite persistant.
    """

    def __init__(
        self,
        *,
        key: bytes,
        scope: str,
        registry_path: str,
    ) -> None:
        self._key = key
        self._scope = scope
        self._registry = ScopeRegistry(key=key, scope=scope, registry_path=registry_path)
        self._engine = Engine(key=key, scope=scope, registry=self._registry)

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
        """
        ac = AhoCorasick.from_registry(self._registry)
        hits = ac.find(text)

        # Substitution de droite à gauche pour préserver les offsets.
        replacements: list[tuple[int, int, str]] = []
        for hit in hits:
            if not self._registry.contains(hit.substitute):
                continue
            record = self._registry.lookup(hit.substitute)
            if record is None:
                continue
            etype = EntityType.coerce(record.entity_type)
            if etype not in _TYPES:
                continue
            decrypt_fn = _TYPES[etype].decrypt
            clear = decrypt_fn(hit.substitute, key=self._key, scope=self._scope)
            replacements.append((hit.start, hit.end, clear))

        # Trier par position décroissante (droite à gauche) pour préserver offsets.
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
