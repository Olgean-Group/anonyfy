"""Moteur d'orchestration des substituts (phase 08 + 13).

Orchestre la détection (validateurs phase 05/06 + contextuels phase 12/13),
l'arbitrage des chevauchements (phase 08/13 ``resolve_overlaps``), le chiffrement
FPE (phase 07) et non-FPE (phase 13 permutation/keystream), l'enregistrement
dans le registre (phase 10 ``register_fpe``) et la substitution droite-à-gauche.

Types couverts:
- FPE (D2 grands domaines): SIRET, SIREN, NIR, IBAN, TVA, CB, téléphone.
- Gazetteer (D22 permutation index): patronyme, prénom, commune, voie.
- Plaque SIV (D2/D22 permutation [0,1000)).
- Référence dossier (D2/D22 XOR keystream).
- Email local-part (D9/D22 permutation base38 + repli keystream).
- Date (D8/D22 permutation bucket, jour clampé [1,28]).

Le démasquage est porté par ``Vault`` (Aho-Corasick + registre + decrypt).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

from anonyfy.detect.context import dates_text, places, triggers
from anonyfy.detect.context import email as email_ctx
from anonyfy.detect.gazetteers.loader import (
    load_communes,
    load_noms,
    load_prenoms,
    load_voies,
)
from anonyfy.detect.validators import cb, iban, nir, phone, plate, reference, siren, tva
from anonyfy.detect.validators import date as date_val
from anonyfy.resolve.arbitrage import resolve_overlaps
from anonyfy.surrogate import fpe
from anonyfy.surrogate.case_pattern import classify_case
from anonyfy.surrogate.date_cipher import DateCipher
from anonyfy.surrogate.email_cipher import EmailCipher
from anonyfy.surrogate.gazetteer_cipher import GazetteerCipher
from anonyfy.surrogate.plate_cipher import PlateCipher
from anonyfy.surrogate.reference_cipher import ReferenceCipher
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

# Types gazetteer nécessitant un flag casse (D24): permutation restitue la forme
# majuscule du gazetteer; le pattern casse permet de restituer la casse originale.
_GAZETTEER_TYPES = frozenset(
    {EntityType.PATRONYME, EntityType.PRENOM, EntityType.COMMUNE, EntityType.VOIE}
)


class Engine:
    """Moteur de masquage (phase 08 + 13).

    Détecte tous les types (FPE + non-FPE), arbitre les chevauchements, chiffre
    par FPE ou permutation/keystream, enregistre chaque substitut au registre
    (invariant 4), et substitue de droite à gauche pour préserver les offsets.
    """

    def __init__(
        self,
        *,
        key: bytes,
        scope: str,
        registry: ScopeRegistry,
        reference_patterns: list[str] | None = None,
    ) -> None:
        self._key = key
        self._scope = scope
        self._registry = registry
        self._reference_validator = (
            reference.ReferenceValidator(reference_patterns) if reference_patterns else None
        )
        # Ciphers non-FPE (construits une fois; gazetteers cached).
        self._cipher_patronyme = GazetteerCipher(key, scope, "patronyme", load_noms())
        self._cipher_prenom = GazetteerCipher(key, scope, "prenom", load_prenoms())
        self._cipher_commune = GazetteerCipher(key, scope, "commune", load_communes())
        self._cipher_voie = GazetteerCipher(key, scope, "voie", load_voies())
        self._cipher_plate = PlateCipher(key, scope)
        self._cipher_reference = ReferenceCipher(key, scope)
        self._cipher_email = EmailCipher(key, scope)
        self._cipher_date = DateCipher(key, scope)

    def mask(self, text: str, *, observe: bool = False) -> MaskedText:
        """Masque tous les identifiants détectés dans ``text``.

        Détecte → arbitre → chiffre → registre → substitution droite-à-gauche.
        Renvoie un ``MaskedText`` dont ``.text`` contient les substituts (jamais
        le clair, invariant 1) et ``.entities`` pointe vers les substituts réels.
        Les valeurs non masquables (nom inconnu du gazetteer, format invalide)
        sont laissées en clair (choix D22(ii), fuite résiduelle documentée).

        Si ``observe=True`` (phase 17, PRD F7): détecte et arbitre seulement, ne
        substitue rien, ne peuple pas le registre. Renvoie un ``MaskedText``
        dont ``.text`` == texte original inchangé et ``.entities`` == spans
        détectés (avec leur confidence/rule_id de détection, non substitués).
        """
        spans = self._detect_all(text)
        resolved = resolve_overlaps(spans)

        if observe:
            # Mode observation (phase 17): détection seule, pas de substitution,
            # pas de registre. Les offsets pointent vers le texte original.
            entities = tuple(resolved)
            return MaskedText(text=text, entities=entities)

        substitutions: list[tuple[int, int, str, EntityType]] = []
        for span in resolved:
            substitute = self._encrypt_span(span)
            if substitute is None:
                continue
            # D23 garde-fou: un point fixe (substitut == clair) est une fuite
            # résiduelle rare (Feistel != derangement). Alerte non silencieuse;
            # le masquage continue avec le point fixe (pas d'exception).
            if substitute == span.value:
                warnings.warn(
                    f"Point fixe permutation: {span.type.value} '{span.value}' "
                    f"non masqué (substitut == clair)",
                    stacklevel=2,
                )
            case_pattern = classify_case(span.value) if span.type in _GAZETTEER_TYPES else None
            self._registry.register_fpe(
                span.type.value,
                span.value,
                surrogate=substitute,
                case_pattern=case_pattern,
            )
            substitutions.append((span.start, span.end, substitute, span.type))

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
                    rule_id=f"mask-{etype.value.lower()}",
                    confidence=1.0,
                )
            )

        entities.sort(key=lambda s: s.start)
        return MaskedText(text=masked, entities=tuple(entities))

    def _encrypt_span(self, span: Span) -> str | None:
        """Chiffre un span selon son type. Retourne le substitut ou None."""
        etype = span.type
        if etype in _TYPES:
            encrypt_fn = _TYPES[etype].encrypt
            return encrypt_fn(span.value, key=self._key, scope=self._scope)
        if etype == EntityType.PATRONYME:
            return self._cipher_patronyme.encrypt(span.value)
        if etype == EntityType.PRENOM:
            return self._cipher_prenom.encrypt(span.value)
        if etype == EntityType.COMMUNE:
            return self._cipher_commune.encrypt(span.value)
        if etype == EntityType.VOIE:
            return self._cipher_voie.encrypt(span.value)
        if etype == EntityType.PLAQUE_SIV:
            return self._cipher_plate.encrypt(span.value)
        if etype == EntityType.REFERENCE_DOSSIER:
            return self._cipher_reference.encrypt(span.value)
        if etype == EntityType.EMAIL:
            sub, _mode = self._cipher_email.encrypt(span.value)
            return sub
        if etype == EntityType.DATE:
            return self._cipher_date.encrypt(span.value)
        return None

    def decrypt_surrogate(self, etype: EntityType, surrogate: str) -> str | None:
        """Déchiffre un substitut selon son type (pour Vault.unmask)."""
        if etype in _TYPES:
            decrypt_fn = _TYPES[etype].decrypt
            return decrypt_fn(surrogate, key=self._key, scope=self._scope)
        if etype == EntityType.PATRONYME:
            return self._cipher_patronyme.decrypt(surrogate)
        if etype == EntityType.PRENOM:
            return self._cipher_prenom.decrypt(surrogate)
        if etype == EntityType.COMMUNE:
            return self._cipher_commune.decrypt(surrogate)
        if etype == EntityType.VOIE:
            return self._cipher_voie.decrypt(surrogate)
        if etype == EntityType.PLAQUE_SIV:
            return self._cipher_plate.decrypt(surrogate)
        if etype == EntityType.REFERENCE_DOSSIER:
            return self._cipher_reference.decrypt(surrogate)
        if etype == EntityType.EMAIL:
            mode = _detect_email_mode(surrogate)
            return self._cipher_email.decrypt(surrogate, mode)
        if etype == EntityType.DATE:
            return self._cipher_date.decrypt(surrogate)
        return None

    def detect(self, text: str) -> list[Span]:
        """Détecte et arbitre les spans de ``text`` sans substituer (phase 17).

        Renvoie les spans résolus (non chevauchants, triés par position) avec
        leur confidence/rule_id de détection. Ne modifie pas le registre.
        Utilisé par ``Vault`` pour la policy de fermeture (strict/permissive)
        et le mode observation.
        """
        return resolve_overlaps(self._detect_all(text))

    def _detect_all(self, text: str) -> list[Span]:
        """Détecte tous les identifiants (FPE + non-FPE)."""
        spans: list[Span] = []
        for info in _TYPES.values():
            spans.extend(info.detect(text))
        spans.extend(triggers.apply(text))
        spans.extend(places.detect(text))
        spans.extend(date_val.detect(text))
        spans.extend(dates_text.detect(text))
        spans.extend(email_ctx.detect(text))
        spans.extend(plate.detect(text))
        if self._reference_validator is not None:
            spans.extend(self._reference_validator.detect(text))
        return spans


_HEX_CHARS = set("0123456789abcdef")


def _detect_email_mode(substitute: str) -> str:
    """Détecte le mode email (perm vs keystream) heuristiquement.

    Le local-part keystream est hex pur (sub_bytes.hex()). Le local-part perm
    contient généralement des lettres non-hex (g, h, i..., +, ., '). Heuristique:
    si le local-part est hex pur et de longueur paire, keystream; sinon perm.
    """
    localpart = substitute.split("@", 1)[0]
    if len(localpart) % 2 == 0 and localpart and all(c in _HEX_CHARS for c in localpart):
        return "keystream"
    return "perm"
