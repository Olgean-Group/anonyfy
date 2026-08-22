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

import hashlib
import hmac
import re
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
from anonyfy.detect.normalize import Run, build_template, tokenize_runs
from anonyfy.detect.validators import cb, iban, nir, phone, plate, reference, siren, tva
from anonyfy.detect.validators import date as date_val
from anonyfy.resolve.arbitrage import resolve_overlaps
from anonyfy.surrogate import fpe
from anonyfy.surrogate.case_pattern import classify_case
from anonyfy.surrogate.date_cipher import DateCipher
from anonyfy.surrogate.email_cipher import EmailCipher
from anonyfy.surrogate.gazetteer_cipher import GazetteerCipher
from anonyfy.surrogate.permutation import Permutation
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

# NIR Corse (2A/2B) - detection par forme (OBJ-REC-102): les exemples du critere
# ont des cles invalides (NIR façonnés); on detecte la forme (15-16 car. avec 2A/2B
# en dept) pour masquer sans fuite, sans exiger une cle valide. Le run capte les
# tokens 2A/2B; ce regex couvre les formes contigues et (via projection) espacees.
_NIR_2A_RE = re.compile(r"(?<!\d)([1-9]\d{2}\d{2}(?:2A|2B)\d{3}\d{3}\d{2,3})(?!\d)")
_NIR_2A_RULE = "nir-2a-shape"

# Validateurs structurés FPE appliqués par run isolé (phase 24). NIR (strict,
# cle valide) est appliqué sur la projection pour les formes espacees sans 2A.
_FPE_RUN_DETECTORS: tuple[tuple[EntityType, object, str], ...] = (
    (EntityType.SIREN, siren.detect, "siren-luhn"),
    (EntityType.SIRET, siren.detect_siret, "siret-luhn"),
    (EntityType.IBAN, iban.detect, "iban-mod97"),
    (EntityType.TVA, tva.detect, "tva-fr-key"),
    (EntityType.CARTE_BANCAIRE, cb.detect, "cb-luhn"),
    (EntityType.TELEPHONE, phone.detect, "phone-format"),
    (EntityType.NIR, nir.detect, "nir-mod97"),
)


# Phase 30 — S4: Permutation keyée sur [0, 100000) pour les CP (5 chiffres).
# L'indice chiffré est stocké dans ``clear_index`` du registre; le substitut
# (5 chiffres du département de la commune substituée) est un « handle » unique.
# Au unmask, ``clear_index`` -> ``Permutation.decrypt`` -> CP clair.
_CP_DOMAIN = 100000
_CP_PERM_CACHE: dict[tuple[bytes, str], Permutation] = {}


def _cp_permutation(key: bytes, scope: str) -> Permutation:
    """Permutation keyée sur [0, 100000) pour le chiffrement réversible des CP."""
    cache_key = (bytes(key), scope)
    perm = _CP_PERM_CACHE.get(cache_key)
    if perm is None:
        perm = Permutation(key=key, scope=scope, entity_type="code_postal", n=_CP_DOMAIN)
        _CP_PERM_CACHE[cache_key] = perm
    return perm


def _cp_prefix(dept: str) -> str:
    """Préfixe CP (2 chiffres) d'un département. Corse 2A/2B -> « 20 »."""
    return "20" if dept in ("2A", "2B") else dept


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
        # Phase 27 OBJ-REC-107: lazy loading par type. Les ciphers gazetteer
        # ne sont construits qu'au premier usage (économise ~220 Mo de RAM si
        # un Vault ne masque que des types FPE, et accélère l'init froid).
        self._cipher_patronyme: GazetteerCipher | None = None
        self._cipher_prenom: GazetteerCipher | None = None
        self._cipher_commune: GazetteerCipher | None = None
        self._cipher_voie: GazetteerCipher | None = None
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
        pairs = self._detect_all_with_format(text)
        spans = [s for s, _ in pairs]
        # format_pattern par span (identifié par id; resolve_overlaps renvoie les
        # memes objets, donc id est stable à travers l'arbitrage).
        fp_map: dict[int, str | None] = {id(s): fp for s, fp in pairs}
        resolved = resolve_overlaps(spans)

        if observe:
            # Mode observation (phase 17): détection seule, pas de substitution,
            # pas de registre. Les offsets pointent vers le texte original.
            entities = tuple(resolved)
            return MaskedText(text=text, entities=entities)

        substitutions: list[tuple[int, int, str, EntityType]] = []
        # Phase 30 — S4: pré-calcul des substituts CP composites (dépendent du
        # département de la commune substituée). Le CP n'est pas chiffré par
        # ``_encrypt_span`` mais par une Permutation dont l'indice chiffré est
        # stocké dans ``clear_index`` du registre (réversibilité).
        cp_data = self._compute_cp_surrogates(resolved)
        for span in resolved:
            if span.type == EntityType.CODE_POSTAL and id(span) in cp_data:
                surrogate, encrypted_idx = cp_data[id(span)]
                if surrogate is None:
                    continue
                self._registry.register_fpe(
                    span.type.value,
                    span.value,
                    surrogate=surrogate,
                    clear_index=encrypted_idx,
                )
                substitutions.append((span.start, span.end, surrogate, span.type))
                continue
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
                format_pattern=fp_map.get(id(span)),
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

    def _build_cipher(self, kind: str, loader) -> GazetteerCipher:
        """Construit un GazetteerCipher paresseusement (OBJ-REC-107)."""
        return GazetteerCipher(self._key, self._scope, kind, loader())

    def _encrypt_span(self, span: Span) -> str | None:
        """Chiffre un span selon son type. Retourne le substitut ou None."""
        etype = span.type
        # NIR Corse 2A/2B (OBJ-REC-102): FPE digits ne supporte pas les lettres;
        # on substitue 2A->19 / 2B->18 puis on chiffre la forme digit. Pour un
        # NIR 15 car. (cle 2) -> encrypt_nir; pour 16 car. (cle 3, exemples du
        # critere) -> encrypt_cb (16 digits Luhn). Le substitut est all-digits
        # (sans 2A); le format_pattern restitue le 2A au unmask.
        if etype == EntityType.NIR and ("2A" in span.value or "2B" in span.value):
            digit = span.value.replace("2A", "19").replace("2B", "18")
            if len(digit) == 15:
                return fpe.encrypt_nir(digit, key=self._key, scope=self._scope)
            if len(digit) == 16:
                return fpe.encrypt_cb(digit, key=self._key, scope=self._scope)
            return None
        if etype in _TYPES:
            encrypt_fn = _TYPES[etype].encrypt
            return encrypt_fn(span.value, key=self._key, scope=self._scope)
        if etype == EntityType.PATRONYME:
            if self._cipher_patronyme is None:
                self._cipher_patronyme = self._build_cipher("patronyme", load_noms)
            return self._cipher_patronyme.encrypt(span.value)
        if etype == EntityType.PRENOM:
            if self._cipher_prenom is None:
                self._cipher_prenom = self._build_cipher("prenom", load_prenoms)
            return self._cipher_prenom.encrypt(span.value)
        if etype == EntityType.COMMUNE:
            if self._cipher_commune is None:
                self._cipher_commune = self._build_cipher("commune", load_communes)
            return self._cipher_commune.encrypt(span.value)
        if etype == EntityType.VOIE:
            if self._cipher_voie is None:
                self._cipher_voie = self._build_cipher("voie", load_voies)
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
        # CODE_POSTAL: géré par le pré-pass ``_compute_cp_surrogates`` dans mask;
        # tombe sur le return None par défaut (pas de cipher direct).
        return None

    def _compute_cp_surrogates(self, resolved: list[Span]) -> dict[int, tuple[str | None, int]]:
        """Phase 30 — S4: pré-calcul des substituts CP composites.

        Pour chaque CP couplé à une commune, le substitut est un CP du département
        de la commune substituée (cohérence, PRD §7). L'indice chiffré (Permutation
        sur [0, 100000)) est stocké dans ``clear_index`` du registre pour la
        réversibilité: au unmask, ``clear_index`` -> ``Permutation.decrypt`` -> CP clair.

        Pour un CP après déclencheur sans commune, un département aléatoire est
        choisi (HMAC-déterministe), différent du département original pour éviter
        la fuite.

        Retourne ``{id(span): (surrogate, encrypted_idx)}``. Le surrogate est un
        CP à 5 chiffres du bon département (ou None si non masquable).
        """
        out: dict[int, tuple[str | None, int]] = {}
        cps = [s for s in resolved if s.type == EntityType.CODE_POSTAL]
        if not cps:
            return out
        communes = [s for s in resolved if s.type == EntityType.COMMUNE]
        gaz = load_communes()
        perm = _cp_permutation(self._key, self._scope)
        for cp in cps:
            encrypted_idx = perm.encrypt(int(cp.value))
            # Trouver la commune couplée la plus proche.
            dept = self._coupled_dept(cp, communes, gaz)
            if dept is None:
                # Trigger-only: dept aléatoire (HMAC), != dept original.
                dept = self._random_dept(cp.value)
            prefix = _cp_prefix(dept)
            suffix_len = 5 - len(prefix)
            base_suffix = encrypted_idx % (10**suffix_len)
            # Sondage linéaire pour éviter collisions et point fixe.
            surrogate = None
            for probe in range(10**suffix_len):
                suffix = (base_suffix + probe) % (10**suffix_len)
                cand = prefix + str(suffix).zfill(suffix_len)
                if cand == cp.value:
                    continue  # éviter point fixe
                if self._registry.contains(cand):
                    continue  # déjà attribué à un autre clair
                surrogate = cand
                break
            if surrogate is None:
                # Tous les candidats sont pris ou points fixes (improbable).
                surrogate = prefix + str(base_suffix).zfill(suffix_len)
            out[id(cp)] = (surrogate, encrypted_idx)
        return out

    def _coupled_dept(self, cp: Span, communes: list[Span], gaz) -> str | None:
        """Département de la commune substituée couplée au CP, ou None.

        Chiffre la commune pour obtenir son substitut, puis lit le département
        du substitut dans le gazetteer. Retourne None si aucune commune couplée
        ou si le substitut est inconnu du gazetteer.
        """
        if not communes:
            return None
        # Commune la plus proche du CP (avant ou après).
        best: Span | None = None
        best_gap = 10**9
        for c in communes:
            gap = max(c.start - cp.end, cp.start - c.end)
            if 0 <= gap < best_gap:
                best = c
                best_gap = gap
        if best is None:
            return None
        commune_sub = self._encrypt_span(best)
        if commune_sub is None or commune_sub.casefold() not in gaz:
            return None
        return gaz[commune_sub.casefold()].departement

    def _random_dept(self, cp_clear: str) -> str:
        """Département aléatoire (HMAC-déterministe), != dept du CP clair."""
        original_dept = cp_clear[:2] if len(cp_clear) >= 2 else ""
        msg = self._scope.encode("utf-8") + b"\x00code_postal_dept\x00" + cp_clear.encode("utf-8")
        digest = hmac.new(self._key, msg, hashlib.sha256).digest()
        dept_num = int.from_bytes(digest[:2], "big") % 96 + 1  # 01-96
        dept = f"{dept_num:02d}"
        if dept == original_dept:
            dept = f"{(dept_num % 95) + 1:02d}"
        return dept

    def decrypt_surrogate(self, etype: EntityType, surrogate: str) -> str | None:
        """Déchiffre un substitut selon son type (pour Vault.unmask)."""
        # NIR Corse 2A/2B (OBJ-REC-102): le substitut 16-digit (cle 3) a été
        # chiffré via encrypt_cb; on dispatch par longueur. Le substitut 15-digit
        # (cle 2, 2A ou non) -> decrypt_nir. La restitution du 2A est faite par le
        # format_pattern dans Vault.unmask (reinsert_template).
        if etype == EntityType.NIR:
            if len(surrogate) == 16:
                return fpe.decrypt_cb(surrogate, key=self._key, scope=self._scope)
            return fpe.decrypt_nir(surrogate, key=self._key, scope=self._scope)
        if etype in _TYPES:
            decrypt_fn = _TYPES[etype].decrypt
            return decrypt_fn(surrogate, key=self._key, scope=self._scope)
        if etype == EntityType.PATRONYME:
            if self._cipher_patronyme is None:
                self._cipher_patronyme = self._build_cipher("patronyme", load_noms)
            return self._cipher_patronyme.decrypt(surrogate)
        if etype == EntityType.PRENOM:
            if self._cipher_prenom is None:
                self._cipher_prenom = self._build_cipher("prenom", load_prenoms)
            return self._cipher_prenom.decrypt(surrogate)
        if etype == EntityType.COMMUNE:
            if self._cipher_commune is None:
                self._cipher_commune = self._build_cipher("commune", load_communes)
            return self._cipher_commune.decrypt(surrogate)
        if etype == EntityType.VOIE:
            if self._cipher_voie is None:
                self._cipher_voie = self._build_cipher("voie", load_voies)
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
        if etype == EntityType.CODE_POSTAL:
            # Phase 30 — S4: l'indice chiffré (Permutation) est stocké dans
            # ``clear_index`` du registre. Le substitut (5 chiffres du dept de
            # la commune substituée) est un « handle » unique; la réversibilité
            # passe par ``clear_index`` -> ``Permutation.decrypt`` -> CP clair.
            record = self._registry.lookup(surrogate)
            if record is None:
                return None
            perm = _cp_permutation(self._key, self._scope)
            return str(perm.decrypt(record.clear_index)).zfill(5)
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
        """Détecte tous les identifiants (FPE + non-FPE), sans empreinte de format.

        Raccourci de ``_detect_all_with_format`` qui ne renvoie que les spans
        (pour ``detect``/observe, qui n'ont pas besoin du format_pattern).
        """
        return [s for s, _ in self._detect_all_with_format(text)]

    def _detect_all_with_format(self, text: str) -> list[tuple[Span, str | None]]:
        """Détecte tous les identifiants avec empreinte de formatage (phase 24).

        Renvoie une liste de (span, format_pattern). Le format_pattern (template
        de séparateurs, OBJ-REC-101) permet au unmask de restituer la forme
        séparée d'origine; ``None`` si le span n'avait pas de séparateurs.
        Les types non-FPE (gazetteer, date, etc.) ont ``format_pattern=None``.
        """
        spans: list[tuple[Span, str | None]] = []
        spans.extend(self._detect_structured_runs(text))
        # Types non-FPE: pas de format_pattern (pas de séparateurs moteur).
        for span in triggers.apply(text):
            spans.append((span, None))
        for span in places.detect(text):
            spans.append((span, None))
        for span in date_val.detect(text):
            spans.append((span, None))
        for span in dates_text.detect(text):
            spans.append((span, None))
        for span in email_ctx.detect(text):
            spans.append((span, None))
        for span in plate.detect(text):
            spans.append((span, None))
        if self._reference_validator is not None:
            for span in self._reference_validator.detect(text):
                spans.append((span, None))
        return spans

    def _detect_structured_runs(self, text: str) -> list[tuple[Span, str | None]]:
        """Détecte les types FPE structurés via runs isolés (phase 24, B1).

        Tokenise les runs (digits + séparateurs + 2A/2B + préfixe +/FR), applique
        les validateurs structurés sur la projection compacte de chaque run isolé
        (OBJ-REC-105: pas de fusion entre runs), remappe les spans vers les
        positions originales via la table d'offsets, et calcule le format_pattern
        (template) pour restituer la forme séparée au unmask (OBJ-REC-101).
        """
        out: list[tuple[Span, str | None]] = []
        for run in tokenize_runs(text):
            proj = run.projection
            # Validateurs FPE (regex avec lookaround) sur la projection isolee.
            for _etype, detect_fn, _rule_id in _FPE_RUN_DETECTORS:
                for sp in detect_fn(proj):
                    out.append(self._remap_span(sp, run, text))
            # NIR Corse 2A/2B par forme (OBJ-REC-102): cle non exigee.
            for m in _NIR_2A_RE.finditer(proj):
                value = m.group(1)
                sp = Span(
                    start=m.start(1),
                    end=m.end(1),
                    type=EntityType.NIR,
                    value=value,
                    rule_id=_NIR_2A_RULE,
                    confidence=0.9,
                )
                out.append(self._remap_span(sp, run, text))
            # SIRET en fenetre glissante (OBJ-REC-105 chiffres collés): un SIRET
            # 14 chiffres valide peut etre un prefixe d'un nombre plus long; on
            # le detecte pour le masquer (substitut != clair, pas de point fixe).
            for i in range(len(proj) - 13):
                cand = proj[i : i + 14]
                if siren.validate_siret(cand) and (i == 0 or not proj[i - 1].isdigit()):
                    sp = Span(
                        start=i,
                        end=i + 14,
                        type=EntityType.SIRET,
                        value=cand,
                        rule_id="siret-luhn-window",
                        confidence=1.0,
                    )
                    out.append(self._remap_span(sp, run, text))
        return out

    @staticmethod
    def _remap_span(sp: Span, run: Run, text: str) -> tuple[Span, str | None]:
        """Remappe un span (coordonnées projection) vers le texte original.

        Renvoie (span_remappé, format_pattern). Le span remappé a des offsets
        absolus dans ``text`` et ``value`` = la projection compacte (le clair
        compact passé à FPE). Le format_pattern est le template de séparateurs
        pour restituer la forme séparée au unmask (``None`` si pas de séparateurs).
        """
        orig_start = run.offset_table[sp.start]
        orig_end = run.offset_table[sp.end - 1] + 1
        remapped = Span(
            start=orig_start,
            end=orig_end,
            type=sp.type,
            value=sp.value,
            rule_id=sp.rule_id,
            confidence=sp.confidence,
        )
        fp = build_template(text, run, sp.start, sp.end)
        return remapped, fp


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
