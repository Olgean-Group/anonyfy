"""Moteur d'orchestration des substituts structurés (phase 08).

Orchestre la détection (validateurs phase 05/06), le chiffrement FPE (phase 07),
l'enregistrement dans le registre (phase 10 ``register_fpe``) et l'arbitrage des
chevauchements (phase 08 ``resolve_overlaps``).

Le moteur est responsable du masquage (mask) d'un texte: il détecte les
identifiants structurés, arbitre les chevauchements, chiffre par FPE, enregistre
chaque substitut FPE émis dans le registre (invariant 4), et substitue de droite
à gauche pour préserver les offsets (architecture §4).

Le démasquage (unmask) est porté par ``Vault`` qui s'appuie sur l'automate
Aho-Corasick (phase 10b) pour retrouver les substituts et sur le registre pour
l'appartenance (invariant 4).

Référence: PLAN.md phase 08, architecture §4, invariants 1/3/4.
"""

from __future__ import annotations

from dataclasses import dataclass

from anonyfy.detect.validators import cb, iban, nir, phone, siren, tva
from anonyfy.resolve.arbitrage import resolve_overlaps
from anonyfy.surrogate import fpe
from anonyfy.surrogate.registry import ScopeRegistry
from anonyfy.types import EntityType, MaskedText, Span

__all__ = ["Engine", "TypeInfo"]


@dataclass(frozen=True, slots=True)
class TypeInfo:
    """Métadonnées d'un type structuré FPE: validateur et fonctions FPE."""

    entity_type: EntityType
    detect: object  # Callable[[str], list[Span]]
    encrypt: object  # Callable[[str, bytes, str], str]
    decrypt: object  # Callable[[str, bytes, str], str]


# Table de dispatch des types structurés FPE couverts en phase 08 (D2).
# Chaque type: son validateur (detect), son encrypt FPE et son decrypt FPE.
_TYPES: dict[EntityType, TypeInfo] = {
    EntityType.SIRET: TypeInfo(
        EntityType.SIRET, siren.detect_siret, fpe.encrypt_siret, fpe.decrypt_siret
    ),
    EntityType.SIREN: TypeInfo(
        EntityType.SIREN, siren.detect, fpe.encrypt_siren, fpe.decrypt_siren
    ),
    EntityType.NIR: TypeInfo(EntityType.NIR, nir.detect, fpe.encrypt_nir, fpe.decrypt_nir),
    EntityType.IBAN: TypeInfo(EntityType.IBAN, iban.detect, fpe.encrypt_iban, fpe.decrypt_iban),
    EntityType.TVA: TypeInfo(EntityType.TVA, tva.detect, fpe.encrypt_tva, fpe.decrypt_tva),
    EntityType.CARTE_BANCAIRE: TypeInfo(
        EntityType.CARTE_BANCAIRE, cb.detect, fpe.encrypt_cb, fpe.decrypt_cb
    ),
    EntityType.TELEPHONE: TypeInfo(
        EntityType.TELEPHONE, phone.detect, fpe.encrypt_phone, fpe.decrypt_phone
    ),
}


class Engine:
    """Moteur de masquage des identifiants structurés (phase 08).

    Détecte les identifiants structurés (D2), arbitre les chevauchements,
    chiffre par FPE (07), enregistre chaque substitut dans le registre (10),
    et substitue de droite à gauche pour préserver les offsets.
    """

    def __init__(self, *, key: bytes, scope: str, registry: ScopeRegistry) -> None:
        self._key = key
        self._scope = scope
        self._registry = registry

    def mask(self, text: str) -> MaskedText:
        """Masque les identifiants structurés de ``text``.

        Détecte → arbitre → FPE → registre → substitution droite-à-gauche.
        Renvoie un ``MaskedText`` dont ``.text`` contient les substituts (jamais le
        clair, invariant 1) et ``.entities`` pointe vers les substituts réels.
        """
        spans = self._detect_all(text)
        resolved = resolve_overlaps(spans)

        # Chiffrer et enregistrer chaque span résolu.
        substitutions: list[tuple[int, int, str, EntityType]] = []
        for span in resolved:
            info = _TYPES[span.type]
            encrypt_fn = info.encrypt  # type: ignore[operator]
            substitute = encrypt_fn(span.value, key=self._key, scope=self._scope)  # type: ignore[call-arg]
            self._registry.register_fpe(span.type.value, span.value, surrogate=substitute)
            substitutions.append((span.start, span.end, substitute, span.type))

        # Substitution de droite à gauche pour préserver les offsets.
        masked = text
        entities: list[Span] = []
        for start, end, substitute, etype in sorted(
            substitutions, key=lambda x: x[0], reverse=True
        ):
            masked = masked[:start] + substitute + masked[end:]
            entities.append(
                Span(
                    start=start,
                    end=start + len(substitute),
                    type=etype,
                    value=substitute,
                    rule_id=f"fpe-{etype.value.lower()}",
                    confidence=1.0,
                )
            )

        # Trier les entities par position (ordre gauche-à-droite pour le consommateur).
        entities.sort(key=lambda s: s.start)
        return MaskedText(text=masked, entities=tuple(entities))

    def _detect_all(self, text: str) -> list[Span]:
        """Détecte tous les identifiants structurés (tous types FPE confondus)."""
        spans: list[Span] = []
        for info in _TYPES.values():
            spans.extend(info.detect(text))  # type: ignore[operator]
        return spans
