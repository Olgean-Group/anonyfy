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

from collections import Counter
from collections.abc import Iterable

from anonyfy.audit import AuditLog
from anonyfy.detect.normalize import reinsert_template
from anonyfy.json_walk import _compile_patterns, walk_mask, walk_unmask
from anonyfy.report import render_report
from anonyfy.resolve.aho_corasick import AhoCorasick
from anonyfy.surrogate.case_pattern import apply_case
from anonyfy.surrogate.engine import Engine
from anonyfy.surrogate.registry import ScopeRegistry
from anonyfy.types import EntityType, MaskedText

__all__ = ["UnresolvedSpanError", "Vault"]

# Seuil de confiance pour « span faible non confirmé par contexte » (phase 17).
# Un span avec déclencheur contextuel fort (« M. », « né(e) le ») a confidence
# 0.9 (>= seuil, fort). Un span sans déclencheur a confidence 0.5 (< seuil,
# faible). Ce seuil est interne au mode policy (pas de changement de
# l'arbitrage phase 13) — à valider par l'orchestrateur (D27 ou suivant).
WEAK_CONFIDENCE_THRESHOLD: float = 0.8


class UnresolvedSpanError(Exception):
    """Levée en ``policy="strict"`` quand un span de confiance faible non
    confirmé par contexte est rencontré (confidence < seuil).

    Référence: PLAN.md phase 17 (PRD F8), critère 3.
    """


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
        audit: AuditLog | None = None,
        policy: str = "permissive",
    ) -> None:
        if policy not in ("permissive", "strict"):
            raise ValueError(f"policy doit être 'permissive' ou 'strict', reçu {policy!r}")
        self._key = key
        self._scope = scope
        self._policy = policy
        self._registry = ScopeRegistry(key=key, scope=scope, registry_path=registry_path)
        self._engine = Engine(
            key=key,
            scope=scope,
            registry=self._registry,
            reference_patterns=reference_patterns,
        )
        self._audit = audit
        self._type_counts: Counter = Counter()
        self._rule_ids: set[str] = set()
        self._mask_calls = 0

    def mask(self, text: str, *, observe: bool = False) -> MaskedText:
        """Masque les identifiants structurés de ``text``.

        Renvoie un ``MaskedText``: ``.text`` contient les substituts FPE (jamais
        le clair, invariant 1), ``.entities`` pointe vers les substituts réels.

        Si ``observe=True`` (phase 17, PRD F7): détecte les spans, les journalise
        (audit), ne substitue rien, ne peuple pas le registre. ``.text`` est le
        texte original inchangé, ``.entities`` contient les spans détectés (non
        substitués, avec leur confidence/rule_id de détection).

        Si un ``AuditLog`` a été fourni au constructeur, enregistre une ligne
        d'audit (méta uniquement: scope, compte par type, rule_ids, empreinte
        HMAC-SHA-256(key, text), et avertissement sur spans faibles en policy
        permissive). Ni le clair ni les substituts ne sont écrits (D10, invariant 1).

        Si ``policy="strict"`` et qu'un span de confiance faible non confirmé par
        contexte (confidence < seuil) est rencontré, lève ``UnresolvedSpanError``.
        """
        if observe:
            result = self._engine.mask(text, observe=True)
            self._mask_calls += 1
            for span in result.entities:
                self._type_counts[span.type] += 1
                self._rule_ids.add(span.rule_id)
            if self._audit is not None:
                self._audit.record(
                    key=self._key,
                    text=text,
                    scope=self._scope,
                    entities=result.entities,
                )
            return result

        # Non-observe: vérifier la policy sur les spans détectés avant substitution.
        resolved = self._engine.detect(text)
        weak = [s for s in resolved if s.confidence < WEAK_CONFIDENCE_THRESHOLD]
        if self._policy == "strict" and weak:
            types = ", ".join(sorted({s.type.value for s in weak}))
            raise UnresolvedSpanError(
                f"span(s) de confiance faible non confirmé(s) par contexte en "
                f"policy strict: {types} (confidence < {WEAK_CONFIDENCE_THRESHOLD})"
            )

        result = self._engine.mask(text)
        self._mask_calls += 1
        for span in result.entities:
            self._type_counts[span.type] += 1
            self._rule_ids.add(span.rule_id)
        if self._audit is not None:
            weak_meta = [
                {
                    "entity_type": s.type.value,
                    "confidence": s.confidence,
                    "rule_id": s.rule_id,
                }
                for s in weak
            ]
            self._audit.record(
                key=self._key,
                text=text,
                scope=self._scope,
                entities=result.entities,
                weak_spans=weak_meta,
            )
        return result

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

        Phase 26 (OBJ-REC-106): les hits chevauchants sont arbitrés par (match
        exact, longueur décroissante) avant la substitution droite-à-gauche. Un
        match exact (le texte contient le substitut canonique) gagne sur une
        variante de casse de même longueur (ex. ``BONY`` texte vs ``Bony``
        substitut commune). Miroir de l'arbitrage mask (``resolve_overlaps``).
        """
        normalized, offset_map = _normalize_inter_digit_spaces(text)

        ac = AhoCorasick.from_registry(self._registry)
        hits = ac.find(normalized)

        # Mapper les hits vers les positions du texte original et déchiffrer.
        # Le tuple inclut is_exact (match == substitute) pour l'arbitrage: un
        # match exact (le texte contient le substitut canonique) est privilégié
        # sur une variante de casse (ex. "BONY" texte vs "Bony" substitut
        # commune dont la variante upper est "BONY").
        replacements: list[tuple[int, int, str, bool]] = []
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
            # Phase 24 (OBJ-REC-101): restituer la forme séparée d'origine depuis
            # le clair compact + le template de formatage (séparateurs + 2A/2B +
            # 0 de +33 0X). Jamais le clair n'est dans le template (invariant 1).
            if record.format_pattern is not None:
                clear = reinsert_template(clear, record.format_pattern)
            orig_start = offset_map[hit.start]
            orig_end = offset_map[hit.end - 1] + 1
            is_exact = hit.match == hit.substitute
            replacements.append((orig_start, orig_end, clear, is_exact))

        # Phase 26 (OBJ-REC-106): arbitrer les hits chevauchants. Tri par
        # (match exact, longueur décroissante): un match exact (le texte
        # contient le substitut canonique tel quel) gagne sur une variante de
        # casse de même longueur; le hit le plus long gagne les overlaps en
        # général. Miroir de l'arbitrage mask (resolve_overlaps): sans cet
        # arbitrage, un substitut préfixe d'un autre (ex. "BON" dans "BONY")
        # ou une variante de casse (ex. "Bony" vs "BONY") produirait des hits
        # chevauchants et la substitution se marcherait dessus (B2b).
        replacements.sort(key=lambda r: (r[3], r[1] - r[0]), reverse=True)
        resolved: list[tuple[int, int, str, bool]] = []
        for start, end, clear, is_exact in replacements:
            if not any(start < e and s < end for s, e, _, _ in resolved):
                resolved.append((start, end, clear, is_exact))

        # Substitution de droite à gauche pour préserver les offsets.
        resolved.sort(key=lambda x: x[0], reverse=True)
        result = text
        for start, end, clear, _ in resolved:
            result = result[:start] + clear + result[end:]
        return result

    def mask_json(
        self,
        payload: object,
        *,
        exempt: Iterable[str] = (),
    ) -> object:
        """Masque les feuilles ``str`` d'un arbre JSON (phase 18, API v2-ready).

        Parcourt récursivement ``payload`` (dict/list/scalaire) et applique
        ``Vault.mask`` sur chaque feuille ``str`` dont le chemin JSONPath ne
        correspond à aucun motif d'``exempt``. Les clés (dict keys), les valeurs
        structurelles (int/float/bool/null/list/dict) et les chemins exemptés
        ne sont jamais touchés.

        ``exempt`` est une liste de chemins simples (ex.
        ``$.tools[*].function.name``, ``$.model``). ``[*]`` est un wildcard
        d'index de liste. JSONPath avancé (``$..``, ``[?()]``, slicing) n'est
        pas supporté (reporté en v2).

        Le clair ne franchit jamais la frontière (invariant 1): ``mask_json``
        délègue à ``Vault.mask`` qui gère déjà l'audit et la substitution FPE.

        Note: pour la compatibilité tool-calling LLM (PRD §7), l'appelant DOIT
        passer ``exempt=["$.tools[*].function.name"]`` afin de préserver les noms
        de fonctions outillés.
        """
        return walk_mask(payload, self._mask_str, _compile_patterns(exempt))

    def unmask_json(
        self,
        payload: object,
        *,
        exempt: Iterable[str] = (),
    ) -> object:
        """Restitue l'arbre JSON clair à partir d'un arbre masqué (phase 18).

        Parcourt récursivement ``payload`` et applique ``Vault.unmask`` sur
        chaque feuille ``str`` non exemptée. Les chemins exemptés sont laissés
        tels quels (ils correspondent à des valeurs non masquées à l'origine).
        """
        return walk_unmask(payload, self._unmask_str, _compile_patterns(exempt))

    def _mask_str(self, text: str) -> str:
        """Adaptateur str -> str pour walk_mask (délègue à Vault.mask)."""
        return self.mask(text).text

    def _unmask_str(self, text: str) -> str:
        """Adaptateur str -> str pour walk_unmask (délègue à Vault.unmask)."""
        return self.unmask(text)

    def report(self) -> str:
        """Produit un rapport d'activité lisible par un non-développeur (PRD F10).

        Retourne une chaîne Markdown synthétisant l'activité du Vault: types
        rencontrés, volumes, règles actives, version des gazetteers. Structure
        stable pour diff (pas de timestamp variable). Ne contient jamais de
        valeur claire ni de substitut (invariant 1).
        """
        return render_report(
            type_counts=self._type_counts,
            rule_ids=self._rule_ids,
            mask_calls=self._mask_calls,
        )

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
