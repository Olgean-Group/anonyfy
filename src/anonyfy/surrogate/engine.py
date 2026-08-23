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
from anonyfy.surrogate.registry import RegistryError, ScopeRegistry
from anonyfy.types import EntityType, MaskedText, Span, UnresolvedSpanError

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

# Phase 34 — R1 (D34c): critère de « candidat nu ». Un span PATRONYME/PRENOM
# dont la règle est l'un des gazetteers ou le context-capture et dont la
# confidence < seuil (pas de déclencheur à proximité) est un candidat issu du
# seul gazetteur : il ne produit un span qu'en strict (pour lever) ou en observe
# (pour montrer) ; en permissive il est filtré au niveau du masquage (D34b).
# Les spans déclenchés (confidence >= 0.8, dont context-capture à 0.8) ne sont
# pas filtrés par ce critère (D34c/D34e) — ils restent soumis au filtre global
# EXCLUDED_NOMS appliqué en amont (triggers.apply).
_BARE_RULES: frozenset[str] = frozenset({"gazetteer-nom", "gazetteer-prenom", "context-capture"})
# Même seuil que vault.WEAK_CONFIDENCE_THRESHOLD (0.8) — défini localement pour
# éviter un import circulaire engine -> vault.
_BARE_CONFIDENCE_THRESHOLD: float = 0.8


#: Phase 38 — R3 (D38b/D38e): fins de phrase pour la position « initiale »
#: (premier mot d'une phrase). Seule cette position est ambiguë en français
#: (toute phrase commence par une majuscule) — la recette R1.
_SENTENCE_FINAL = frozenset({".", "!", "?", "…", "»", '"', "«"})


def _at_sentence_initial(text: str, start: int) -> bool:
    """True si ``start`` est le premier token d'une phrase (position ambiguë).

    Premier token du texte, ou précédé d'une fin de phrase (`.`, `!`, `?`,
    `…`, guillemets). Une virgule ou un deux-points ne termine PAS une phrase
    (position structurelle, D38c) : le token après est en milieu.
    """
    if start <= 0:
        return True
    i = start - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    return i < 0 or text[i] in _SENTENCE_FINAL


def _is_pure_patronyme(span: Span) -> bool:
    """True si le premier mot du span est absent du gazetteer prénoms (D38e).

    Un PATRONYME pur (nom seul) en initiale de phrase est émis (non ambigu) ;
    un token à la fois PRENOM et PATRONYME reste rejeté (ambiguïté prénom).
    """
    first = span.value.split()[0].casefold()
    return first not in load_prenoms()


# Phase 42 — P1 (D42b/D42c/D42d/D42f): indices contextuels d'adresse pour les
# spans faibles (confidence < 0.8). Un span COMMUNE/VOIE faible n'est émis en
# permissive que s'il porte un indice d'adresse fort ; un type faible sans
# indice enregistré n'est PAS émis (défaut SAFE, D42b).
#
# Verbes d'adresse (indice COMMUNE, D42c) — réconciliés avec
# ``places._CP_TRIGGERS`` (single source of truth, D42f : ``domicilié à `` et
# ``résidant à `` y ont été ajoutés). Divergence justifiée : ``à `` nu reste un
# déclencheur CP (S4) mais PAS un indice COMMUNE ; ``adresse : `` est un indice
# COMMUNE mais pas un déclencheur CP.
_ADDRESS_VERBS: tuple[str, ...] = (
    "domicilié à ",
    "demeurant à ",
    "habite à ",
    "résidant à ",
    "adresse : ",
    # Phase 45 — R5 (D45b/D45h) : formule « Fait à <commune> » (participe passé
    # capitalisé + « à » immédiatement avant la commune). COMMUNE-only : PAS
    # ajouté à ``places._CP_TRIGGERS`` car « à » nu couvre déjà le CP dans
    # « Fait à 16000 Angoulême » (indice (b)). La forme de match insensible à
    # la casse et contrainte au début de ligne est portée par ``_FAIT_A_RE``
    # (D45d) ; la chaîne exacte « Fait à » ci-dessous couvre la forme
    # capitalisée canonique du formulaire.
    "Fait à ",
)
# Fenêtre (caractères) entre la fin du verbe d'adresse et le début de la
# commune : « immédiatement avant » (D42c) = au plus une espace blanche.
_ADDRESS_VERB_WINDOW: int = 1

#: Phase 45 — R5 (D45d) : indice (c) « Fait à <commune> » — participe passé
#: capitalisé en début de ligne + « à » immédiatement avant la commune. Forme
#: imposée : ``(?:^|\n)\s*fait à\s+`` insensible à la casse (matche « Fait à »,
#: « FAIT À », « fait à » en début de ligne/paragraphe). Exclut la prose
#: « il est fait à Paris » (minuscule, milieu de phrase).
_FAIT_A_RE = re.compile(r"(?:^|\n)\s*fait à\s+", re.IGNORECASE)

#: Phase 45 — R5 (D45h(ii)/D45k) : indice (d) « <Commune>, le <date> » en début
#: de ligne — la commune est suivie de ``, le <chiffre>`` (dates en CHIFFRES
#: uniquement). Les dates en toutes lettres (« le vingt-trois août », OBJ-108)
#: restent hors périmètre.
_HEADER_COMMA_LE_RE = re.compile(r", le \d")

# Types de voie en tête d'un span VOIE (indice (a), D42d).
_VOIE_TYPE_WORDS: frozenset[str] = frozenset(
    {"rue", "avenue", "boulevard", "chemin", "impasse", "place"}
)
# Numéro de rue en tête (indice (b), D42d) : une séquence de 1-4 chiffres se
# terminant immédiatement avant le span (« 12 rue de la Paix »). ``\s*$`` borne
# l'écart à une espace blanche (immédiatement avant).
_NUMERO_VOIE_RE = re.compile(r"(?<!\d)(\d{1,4})\s*$")


def _at_line_start(text: str, start: int) -> bool:
    """True si ``start`` est le premier token (non espace) d'une ligne.

    Position 0 du texte, ou précédé d'un ``\n`` (les espaces/tabulations de
    retrait entre le début de ligne et le token sont admises). D45c/D45d : la
    formule d'en-tête et le « Fait à » sont contraints au début de ligne.
    """
    i = start - 1
    while i >= 0 and text[i] in " \t\f":
        i -= 1
    return i < 0 or text[i] == "\n"


def _commune_a_indice_adresse(span: Span, text: str, cps: list[Span]) -> bool:
    """True si le span COMMUNE faible porte un indice d'adresse fort (D42c/D42f).

    (a) un verbe d'adresse se termine immédiatement avant le span
    (``places._trigger_before`` réutilisée, D42f) ; (b) un code postal est
    adjacent au span (``places._cp_near_commune``, D42f) ; (c) la formule
    « Fait à <commune> » en début de ligne (D45d, insensible à la casse) ;
    (d) l'en-tête de lettre « <Commune>, le <date> » en début de ligne (D45h,
    date en chiffres, D45k).
    """
    if places._trigger_before(span.start, text, _ADDRESS_VERBS, _ADDRESS_VERB_WINDOW):
        return True
    if any(places._cp_near_commune(cp.start, cp.end, [span]) for cp in cps):
        return True
    # Phase 45 — R5 (D45d) : indice (c). La formule se termine immédiatement
    # avant la commune (fenêtre ``_ADDRESS_VERB_WINDOW``) ; ``\s+`` a déjà
    # consommé l'espace entre « à » et la commune. Dans « Fait à 16000
    # Angoulême », le CP intercalaire décale la fin du match de plus d'un
    # caractère -> l'indice (b) porte le masquage (D45j, OBJ-107).
    for m in _FAIT_A_RE.finditer(text, 0, span.start):
        if span.start - m.end() <= _ADDRESS_VERB_WINDOW:
            return True
    # Phase 45 — R5 (D45h) : indice (d) — en-tête « <Commune>, le <date> ».
    if _at_line_start(text, span.start) and _HEADER_COMMA_LE_RE.match(text, span.end):
        return True
    return False


def _voie_a_indice(span: Span, text: str) -> bool:
    """True si le span VOIE faible porte un indice (D42d).

    (a) le premier mot du span (casefold) est un type de voie ; (b) un numéro
    de rue (1-4 chiffres) se termine immédiatement avant le span.
    """
    first = span.value.split()[0].casefold()
    if first in _VOIE_TYPE_WORDS:
        return True
    return bool(_NUMERO_VOIE_RE.search(text[: span.start]))


def _is_bare_candidate(span: Span, text: str, cps: list[Span] | None = None) -> bool:
    """True si ``span`` est un candidat nu à rejeter au masquage non-observe.

    Phase 34 — R1 (D34b): un candidat gazetteer seul, sans déclencheur
    (confidence < 0.8), n'était émis en permissive dans AUCUNE position — le
    rappel s'est effondré (R3, recette 0.1.3 : 1,4 % hors contexte).

    Phase 38 — R3 (D38b/D38d/D38e) : le rejet est restreint à la position
    d'initiale de phrase (la position ambiguë), et s'y applique à la PATRONYME
    et au PRENOM : un PATRONYME pur (absent du gazetteer prénoms) est émis (non
    ambigu), un PRENOM ou un token ambigu (PRENOM ET PATRONYME) reste rejeté.

    Milieu de phrase (position non ambiguë) : un candidat nu isolé
    PRENOM/PATRONYME est ÉMIS (D38b littéral, S5-Q1 : « J'ai vu Paul hier. »
    -> Paul masqué). Les faux positifs du corpus négatif (sociétés, lieux,
    voies) sont traités au cas par cas à la détection (marqueurs non personne
    dans triggers.py, arbitrage VOIE), pas en filtrant tous les nus.

    Phase 42 — P1 (D42b/D42c/D42d): généralisation. Un span à ``confidence <
    _BARE_CONFIDENCE_THRESHOLD`` n'est émis en permissive QUE s'il porte un
    indice contextuel enregistré pour son type ; un type sans indice enregistré
    est filtré par défaut (défaut SAFE) :
    - PATRONYME/PRENOM : comportement D38b/D38e ci-dessus (position d'initiale
      de phrase), inchangé ;
    - COMMUNE : verbe d'adresse immédiatement avant ou code postal adjacent
      (D42c, ``_commune_a_indice_adresse``) ;
    - VOIE : type de voie en tête du span ou numéro de rue avant (D42d,
      ``_voie_a_indice``) ;
    - autre type sans indice enregistré : défaut SAFE (filtré).
    ``cps`` : les spans CODE_POSTAL déjà résolus (indice CP adjacent).
    """
    if span.confidence >= _BARE_CONFIDENCE_THRESHOLD:
        return False
    if span.type in (EntityType.PATRONYME, EntityType.PRENOM):
        if span.rule_id not in _BARE_RULES:
            return False
        if not _at_sentence_initial(text, span.start):
            return False
        # Position ambiguë (initiale) : seul un PATRONYME pur est émis (D38e).
        if span.type == EntityType.PATRONYME and _is_pure_patronyme(span):
            return False
        return True
    if span.type == EntityType.COMMUNE:
        return not _commune_a_indice_adresse(span, text, cps if cps is not None else [])
    if span.type == EntityType.VOIE:
        return not _voie_a_indice(span, text)
    # Défaut SAFE (D42b) : un type faible sans indice enregistré n'est pas émis.
    return True


def _filter_bare_candidates(spans: list[Span], text: str) -> list[Span]:
    """D42b : filtre au masquage non-observe les candidats nus de tous types.

    L'invariant généralisé « aucun span à confidence < 0.8 sans indice, quel
    que soit le type » est posé ici, une seule fois, dans la règle d'émission.
    """
    cps = [s for s in spans if s.type == EntityType.CODE_POSTAL]
    return [s for s in spans if not _is_bare_candidate(s, text, cps)]


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

    def mask(self, text: str, *, observe: bool = False, strict: bool = False) -> MaskedText:
        """Masque tous les identifiants détectés dans ``text``.

        Détecte → arbitre → chiffre → registre → substitution droite-à-gauche.
        Renvoie un ``MaskedText`` dont ``.text`` contient les substituts (jamais
        le clair, invariant 1) et ``.entities`` pointe vers les substituts réels.
        Les valeurs non masquables (nom inconnu du gazetteer, format invalide)
        sont laissées en texte (choix D22(ii), fuite résiduelle documentée).

        Si ``observe=True`` (phase 17, PRD F7): détecte et arbitre seulement, ne
        substitue rien, ne peuple pas le registre. Renvoie un ``MaskedText``
        dont ``.text`` == texte original inchangé et ``.entities`` == spans
        détectés (avec leur confidence/rule_id de détection, non substitués).

        Phase 35 — S1 (D35f/D35g/D35h): filet de sûreté global appliqué APRÈS
        la boucle de substitution sur la liste des substitutions (tous les
        chemins: CP, FPE, gazetteer, context-capture). Un substitut final ==
        clair (point fixe, ou registre idempotent d'une version cassée) est une
        fuite: en ``strict`` lève ``UnresolvedSpanError``; en permissive, sonde
        déterministe bornée (max 1000, D35h) jusqu'à un substitut non
        collisionnant (le registre reste le garde-fou), sinon émet un
        ``UserWarning`` (D35g) et laisse le clair en place (dernier recours).
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

        # Phase 34 — R1 (D34b/D34c/D34e) + Phase 38 — R3 (D38b/D38d/D38e) +
        # Phase 42 — P1 (D42b/D42c/D42d): filtrage des candidats nus au niveau
        # du masquage non-observe. Un span à confidence < 0.8 n'est émis que
        # s'il porte un indice contextuel pour son type (défaut SAFE, D42b).
        # Un PATRONYME pur en initiale est émis (D38e) ; un PRENOM ou un token
        # ambigu en initiale est rejeté ; un COMMUNE/VOIE faible n'est émis que
        # sur indice d'adresse fort (verbe d'adresse, CP adjacent, type de
        # voie, numéro de rue). Les spans déclenchés (confidence >= 0.8) et
        # observe/strict (Vault.mask, qui détecte en amont) restent inchangés.
        resolved = _filter_bare_candidates(resolved, text)

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
                # Idempotent: un clair déjà enregistré (ex. entrée d'une version
                # cassée, substitut == clair) renvoie le substitut existant; on
                # utilise le RETOUR pour que le filet global (D35f) voie le
                # point fixe réel (sinon la fuite passerait inaperçue).
                surrogate = self._registry.register_fpe(
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
            # D35f: un point fixe (substitut == clair, Feistel sans dérangement
            # ~1 par gazetteer) n'est PAS enregistré: le filet global le corrige
            # par sondage (D35i), ou lève/avertit en dernier recours (D35h/D35g).
            if substitute.casefold() == span.value.casefold():
                substitutions.append((span.start, span.end, substitute, span.type))
                continue
            case_pattern = classify_case(span.value) if span.type in _GAZETTEER_TYPES else None
            # Le retour de register_fpe est utilisé (idempotence: un même clair
            # renvoie le substitut déjà enregistré, ce qui reste le substitut
            # réel visible du unmask).
            substitute = self._registry.register_fpe(
                span.type.value,
                span.value,
                surrogate=substitute,
                case_pattern=case_pattern,
                format_pattern=fp_map.get(id(span)),
            )
            substitutions.append((span.start, span.end, substitute, span.type))

        # Phase 35 — S1 (D35f/D35g/D35h): filet de sûreté GLOBAL, appliqué
        # APRÈS la boucle de substitution sur la liste complète (tous les
        # chemins: CP, FPE, gazetteer, context-capture). En strict, un substitut
        # final == clair lève (aucune fuite silencieuse); en permissive, sondage
        # déterministe borné (max 1000, D35i/D35h), sinon UserWarning (D35g) et
        # le clair reste en place (dernier recours, jamais en silence).
        if strict:
            for start, end, substitute, etype in substitutions:
                if substitute.casefold() == text[start:end].casefold():
                    raise UnresolvedSpanError(
                        f"span non masquable en policy strict: {etype.value} "
                        f"{text[start:end]!r} (substitut == clair après sondage borné)"
                    )
        else:
            substitutions = self._apply_fixed_point_probe(text, substitutions)

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

    def _cipher_for(self, etype: EntityType) -> GazetteerCipher | None:
        """Cipher gazetteer du type (construit paresseusement), ou None.

        Utilisé par ``_encrypt_span`` et par le sondage du filet (D35f/D35i):
        seuls les types gazetteer ont un ``probe`` réversible.
        """
        if etype == EntityType.PATRONYME:
            if self._cipher_patronyme is None:
                self._cipher_patronyme = self._build_cipher("patronyme", load_noms)
            return self._cipher_patronyme
        if etype == EntityType.PRENOM:
            if self._cipher_prenom is None:
                self._cipher_prenom = self._build_cipher("prenom", load_prenoms)
            return self._cipher_prenom
        if etype == EntityType.COMMUNE:
            if self._cipher_commune is None:
                self._cipher_commune = self._build_cipher("commune", load_communes)
            return self._cipher_commune
        if etype == EntityType.VOIE:
            if self._cipher_voie is None:
                self._cipher_voie = self._build_cipher("voie", load_voies)
            return self._cipher_voie
        return None

    def _encrypt_span(self, span: Span) -> str | None:
        """Chiffre un span selon son type. Retourne le substitut ou None."""
        etype = span.type
        # NIR Corse 2A/2B (OBJ-REC-102): FPE digits ne supporte pas les lettres;
        # on substitue 2A->19 / 2B->18 puis on chiffre la forme digit. Pour un
        # NIR 15 car. (code 2) -> chiffre_nir; pour 16 car. (code 3, exemples du
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
        cipher = self._cipher_for(etype)
        if cipher is not None:
            return cipher.encrypt(span.value)
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

    def _apply_fixed_point_probe(self, text: str, substitutions):
        """D35f/D35g/D35h: corrige (ou signale) les points fixes de la liste.

        Pour chaque entrée dont le substitut final == clair (casefold), sonde un
        substitut non collisionnant (D35i, max 1000 tentatives). Si le sondage
        échoue, émet un ``UserWarning`` APRÈS le sondage (D35g) et retire
        l'entrée (dernier recours: le clair reste en place, mais jamais en
        silence). Les entrées saines sont conservées telles quelles.
        """
        out: list[tuple[int, int, str, EntityType]] = []
        for start, end, substitute, etype in substitutions:
            clear = text[start:end]
            if substitute.casefold() != clear.casefold():
                out.append((start, end, substitute, etype))
                continue
            replacement = self._probe_fixed_point_replacement(clear, etype)
            if replacement is None:
                warnings.warn(
                    f"Point fixe permutation: {etype.value} {clear!r} non masqué "
                    f"(substitut == clair, sondage borné épuisé)",
                    stacklevel=3,
                )
                continue
            out.append((start, end, replacement, etype))
        return out

    def _probe_fixed_point_replacement(
        self, span_value: str, etype: EntityType, max_probes: int = 1000
    ) -> str | None:
        """D35i/D35h: sondage borné d'un substitut non collisionnant != clair.

        Pour un type gazetteer, ``cipher.probe(value, k)`` rend le nom à l'index
        ``perm.encrypt((idx + k) % n)`` (déterministe, bijectif par (idx, k) tant
        que la colonne n'est pas saturée). Le registre reste le garde-fou:
        ``register_fpe`` lève ``RegistryError`` si le candidat est déjà attribué
        à un autre clair (collision -> sondage suivant). Pour un type sans probe
        (FPE, CP, date, email, plaque, référence), renvoie ``None``: le clair est
        déjà enregistré par une version cassée, aucune correction possible.
        """
        cipher = self._cipher_for(etype)
        for k in range(1, max_probes + 1):
            candidate = cipher.probe(span_value, k) if cipher is not None else None
            if candidate is None:
                return None
            if candidate.casefold() == span_value.casefold():
                continue
            try:
                self._registry.register_fpe(
                    etype.value,
                    span_value,
                    surrogate=candidate,
                    case_pattern=(classify_case(span_value) if etype in _GAZETTEER_TYPES else None),
                )
            except RegistryError:
                continue
            return candidate
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
