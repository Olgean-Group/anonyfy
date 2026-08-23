"""Phase 38 — R3 : double corpus de non-régression rappel / précision (D38f, D38h).

La recette 0.1.3 constate que chaque correctif de précision a fait chuter le
rappel (R1 : 100 % -> 1,4 % hors contexte déclenché) et inversement. Tant que
les deux grandeurs ne sont pas gardées ensemble dans la CI, chaque correctif
déplace le problème d'un plateau de la balance à l'autre.

Ce test installe la mesure permanente (PRD « Corrections recette 0.1.3 », D38f) :

- corpus POSITIF : >= 50 patronymes réels du gazetteer noms, répartis sur >= 10
  contextes (>= 5 patronymes par contexte) : avec titre (M., Maître, Mme), sans
  titre en initiale de phrase (PATRONYME pur), couple prénom+nom (Jean X,
  Marie X), liste (« Présents : X »), signature (« Cordialement,<br>X »), cellule
  de tableau (« Nom : X »), énumération de noms. Seuil : rappel >= 0.98.
- corpus NÉGATIF : >= 50 phrases = `CORPUS` existant de
  `test_no_false_positive.py` (30 phrases, réutilisé par import pour ne pas
  diverger) + 24 phrases additionnelles figées au commit RED (D38h) : noms de
  sociétés en milieu, toponymes en milieu, prénoms non personnels en milieu
  (liste du PLAN.md phase 38, lignes 150-188). Seuil : précision >= 0.95.

Oracle négatif (scopé R1, D38f) : une phrase négative est « préservée » si elle
ne contient AUCUN span de type PRENOM ou PATRONYME
(`not any(s.type in (EntityType.PRENOM, EntityType.PATRONYME) for s in m.entities)`).
Les masques COMMUNE/VOIE/CP/FPE sont des masques légitimes (hors périmètre R1)
et sont ignorés par cet oracle.

Mesure du rappel : en mode masquage (non-observe), `span.value` est le
SUBSTITUT et les offsets `span.start/end` ne bornent pas exactement le token
clair (le `end` inclut la suite du mot). La mesure fiable du masquage est
sémantique : un patronyme attendu est « masqué » si son clair (casefold)
n'apparaît plus dans le texte de sortie. Sur le corpus (noms uniques dans la
phrase), c'est exact ; et c'est la grandeur de sûreté réelle (le clair ne
franchit pas la frontière, invariant 1).

Le commit RED (état anonyfy 0.1.3) démontre : corpus négatif VERT (R1 déjà
corrigé) + corpus positif ROUGE (rappel bien en dessous de 0.98). Le commit
GREEN ne modifie pas le corpus négatif (D38h).

Référence : PLAN.md phase 38, D38f-D38h ; `anonyfy_code_review3.md` (R3).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import load_noms
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "acceptance-recall-precision"

# Réutilisation par référence du corpus négatif existant (test_no_false_positive).
# Ne pas dupliquer les phrases : toute divergence entre les deux fichiers casserait
# la non-régression R1 (test_no_false_positive.py) et le corpus négatif ci-dessous.
# `tests/acceptance` n'est pas un package : import par chemin de fichier (D38h :
# source indépendante = le CORPUS existant, pas une copie).
_NEG_SPEC = importlib.util.spec_from_file_location(
    "test_no_false_positive", str(Path(__file__).parent / "test_no_false_positive.py")
)
_neg_base = importlib.util.module_from_spec(_NEG_SPEC)
assert _NEG_SPEC.loader is not None
_NEG_SPEC.loader.exec_module(_neg_base)
CORPUS_NEGATIF: tuple[str, ...] = _neg_base.CORPUS + (
    # --- Noms de sociétés en milieu de phrase (8) : un patronyme de société
    # n'est pas une donnée personnelle. (Liste figée, PLAN phase 38.)
    "La société Dupont a signé le contrat.",
    "Le cabinet Moreau a rendu son avis juridique.",
    "La société Lefebvre et Fils a été placée en liquidation.",
    "Le groupe Bernard a publié ses résultats annuels.",
    "La société Martin a déposé le bilan hier.",
    "Le cabinet Petit a été mandaté pour l'audit.",
    "La société Durand a recruté dix salariés.",
    "Le groupe Robert a cédé sa filiale étrangère.",
    # --- Toponymes / noms de lieux en milieu de phrase (8) : un toponyme n'est
    # pas une donnée personnelle, même s'il est aussi patronyme/prénom.
    "Le train part de Lyon à huit heures.",
    "La réunion se tient à Paris.",
    "Nous avons visité Bordeaux l'été dernier.",
    "Le colis transite par Marseille.",
    "La conférence a lieu à Lille.",
    "Le siège social est situé à Nantes.",
    "La route nationale passe par Tours.",
    "Le festival se déroule à Avignon.",
    # --- Prénoms en milieu non personnel (8) : un token prénom-like utilisé
    # comme commune/lieu/monument n'est pas une donnée personnelle.
    "La clause Pierre du contrat a été modifiée.",
    "La place Marie a été rénovée.",
    "Le quai Bernard est inaccessible.",
    "La rue Victor Hugo est en travaux.",
    "Le boulevard Jean Jaurès est fermé à la circulation.",
    "La tour Eiffel domine la ville.",
    "Le pont Alexandre III est illuminé.",
    "Le mont Saint-Michel attire de nombreux touristes.",
)


# --- Corpus positif : >= 50 patronymes, >= 10 contextes, >= 5 par contexte ---
#
# Patronymes « purs » (noms seuls, ni prénoms ni communes) pour la position
# d'initiale de phrase (D38e) ; vérifiés dans le gazetteer courant : dupont,
# lefebvre, moreau, mercier, fournier, lopez, chevalier, delorme, rousseau,
# garnier.
_PURE = ("Dupont", "Lefebvre", "Moreau", "Mercier", "Fournier")

# Chaque contexte = un couple (étiquette, phrases) avec >= 5 patronymes
# attendus. Le corpus est construit à partir du gazetteer noms (D38g) : vérifié
# ci-dessous.
POSITIF_PAR_CONTEXTE: tuple[tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...] = (
    # 1. avec titre « M. »
    ("titre-m", tuple((f"M. {n} est concerné par le dossier.", (n,)) for n in _PURE)),
    # 2. avec titre « Maître »
    ("titre-maitre", tuple((f"Maître {n} représente le défendeur.", (n,)) for n in _PURE)),
    # 3. avec titre « Mme »
    ("titre-mme", tuple((f"Mme {n} a assisté à la réunion.", (n,)) for n in _PURE)),
    # 4. couple prénom+nom (D38a) — « Jean »
    ("couple-jean", tuple((f"Jean {n} a été reçu ce matin.", (n,)) for n in _PURE)),
    # 5. couple prénom+nom (D38a) — « Marie »
    ("couple-marie", tuple((f"Marie {n} est directrice du projet.", (n,)) for n in _PURE)),
    # 6. initiale de phrase, patronyme pur sans titre (D38e)
    ("initiale", tuple((f"{n} a signé le contrat.", (n,)) for n in _PURE)),
    # 7. liste « Présents : » (D38c)
    ("presentes", tuple((f"Présents : {n}.", (n,)) for n in _PURE)),
    # 8. signature — début de ligne après « Cordialement, » (D38c)
    ("cordialement", tuple((f"Cordialement,\n{n}", (n,)) for n in _PURE)),
    # 9. cellule de tableau « Nom : » (D38c)
    ("nom-cellule", tuple((f"Nom : {n}", (n,)) for n in _PURE)),
    # 10. énumération de noms (D38c) — 2 phrases x 3 noms = 6
    (
        "enumeration",
        (
            ("Présents : Dupont, Lefebvre et Moreau.", ("Dupont", "Lefebvre", "Moreau")),
            ("Présents : Mercier, Fournier et Chevalier.", ("Mercier", "Fournier", "Chevalier")),
        ),
    ),
)

POSITIF: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
    ph for _, contextes in POSITIF_PAR_CONTEXTE for ph in contextes
)
_TOTAL_PATRONYMES = sum(len(attendus) for _, attendus in POSITIF)
_N_CONTEXTES = len(POSITIF_PAR_CONTEXTE)
assert _N_CONTEXTES >= 10, "corpus positif : >= 10 contextes exigés"
assert all(sum(len(a) for _, a in phrases) >= 5 for _, phrases in POSITIF_PAR_CONTEXTE), (
    "chaque contexte >= 5 patronymes"
)
assert _TOTAL_PATRONYMES >= 50, "corpus positif : >= 50 patronymes exigés"
assert all(n.casefold() in load_noms() for n in _PURE), "patronymes tirés du gazetteer noms"


def _patronyme_fuit(attendus: tuple[str, ...], m) -> list[str]:
    """Patronymes attendus ENCORE PRÉSENTS en clair dans le texte masqué
    (non remplacés par un substitut : la donnée franchit la frontière, fuite)."""
    texte = m.text.casefold()
    return [a for a in attendus if a.casefold() in texte]


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


def _phrase_ids() -> list[str]:
    return [f"pos{idx}" for idx in range(len(POSITIF))]


class TestRappelCorpusPositif:
    """Rappel : les patronymes réels du corpus positif sont masqués comme
    PRENOM ou PATRONYME en politique permissive (défaut)."""

    @pytest.mark.parametrize(
        ("phrase", "attendus"), POSITIF, ids=lambda v: v if isinstance(v, str) else "-".join(v)
    )
    def test_patronyme_masque(self, vault, phrase: str, attendus: tuple[str, ...]) -> None:
        m = vault.mask(phrase)
        fuites = _patronyme_fuit(attendus, m)
        assert not fuites, (
            f"patronymes en clair (fuite) dans {phrase!r}: {fuites}. "
            f"Spans : {[(s.type.value, round(s.confidence, 2)) for s in m.entities]}"
        )

    def test_rappel_global_sup_egal_98(self, vault) -> None:
        """D38f : seuil global de rappel >= 0.98, affiché en valeur continue."""
        total = _TOTAL_PATRONYMES
        trouve = 0
        for phrase, attendus in POSITIF:
            m = vault.mask(phrase)
            fuites = set(_patronyme_fuit(attendus, m))
            trouve += len(attendus) - len(fuites)
        rappel = trouve / total
        print(f"rappel={rappel:.3f} (patronymes: {trouve}/{total}, contextes: {_N_CONTEXTES})")
        assert rappel >= 0.98, f"rappel={rappel:.3f} < 0.98 sur {total} patronymes"


def _ids_neg() -> list[str]:
    return [f"neg{idx}" for idx in range(len(CORPUS_NEGATIF))]


class TestPrecisionCorpusNegatif:
    """Précision R1 (oracle scopé) : aucune phrase négative ne contient un span
    PRENOM ou PATRONYME masqué. Les masques COMMUNE/VOIE sont légitimes."""

    @pytest.mark.parametrize("phrase", CORPUS_NEGATIF, ids=_ids_neg())
    def test_aucun_span_prenom_patronyme(self, vault, phrase: str) -> None:
        m = vault.mask(phrase)
        problemes = [
            (s.type.value, round(s.confidence, 2))
            for s in m.entities
            if s.type in (EntityType.PRENOM, EntityType.PATRONYME)
        ]
        assert not problemes, f"faux positif PRENOM/PATRONYME dans {phrase!r}: {problemes}"

    def test_precision_globale_sup_egal_95(self, vault) -> None:
        """D38f : seuil global de précision >= 0.95, affiché en valeur continue."""
        total = len(CORPUS_NEGATIF)
        preservees = 0
        rouges: list[str] = []
        for phrase in CORPUS_NEGATIF:
            m = vault.mask(phrase)
            if not any(s.type in (EntityType.PRENOM, EntityType.PATRONYME) for s in m.entities):
                preservees += 1
            else:
                rouges.append(phrase)
        precision = preservees / total
        print(f"precision={precision:.3f} ({preservees}/{total} préservées)")
        if rouges:
            print("phrases rouges :")
            for r in rouges:
                print("  ", r)
        assert precision >= 0.95, f"precision={precision:.3f} < 0.95 sur {total} phrases"
