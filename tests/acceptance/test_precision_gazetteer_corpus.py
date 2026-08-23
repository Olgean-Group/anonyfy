"""Phase 43 — corpus négatif auto-généré par intersection avec les gazetteers (D43a-D43e).

Le corpus négatif existant (phase 38) est figé en dur. Il ne se régénère pas
quand les gazetteers changent, et il ne couvre pas les mots courants qui sont
aussi des entrées de gazetteer (communes, voies, noms, prénoms) : la recette
0.1.4 a montré « Pierre » -> COMMUNE, « douze » -> COMMUNE, « champ » -> VOIE
en prose sans indice d'adresse (P1, corrigé en phase 42).

Ce test installe le corpus négatif RÉGÉNÉRÉ (PRD « Corrections recette 0.1.4 »,
D43a) :

- liste FIGÉE de mots français courants (mapping mot -> phrase ordinaire) : le
  mot est employé dans son sens courant (non personnel, non locatif), sans
  indice contextuel (c'est ce qui en fait un piège P1) ;
- l'intersection est recalculée à chaque exécution avec les quatre gazetteers
  (``load_communes``, ``load_voies``, ``load_noms``, ``load_prenoms``) : chaque
  mot trouvé dans un gazetteer produit sa phrase dans le corpus. Le corpus
  s'adapte donc à l'évolution des gazetteers, rien n'est figé en dur (D43a) ;
- les 3 faux positifs concrets de la recette sont imposés dans la liste (D43c) :
  ``pierre`` -> « La pierre angulaire du dispositif… », ``douze`` -> « … court
  sur douze mois… », ``champ`` -> « Le champ de la mission… » ;
- aucune donnée personnelle réelle : mots courants + phrases synthétiques (D43d).

Oracle (D43b) : une phrase est « préservée » si elle ne contient AUCUN span de
type PRENOM, PATRONYME, COMMUNE ou VOIE. Précision = préservées / total, seuil
>= 0.95, affichée en valeur continue. Les phrases du corpus 43 sont disjointes
des toponymes capitalisés du corpus phase 38 (critère 7) : pas de recouvrement
qui masquerait une divergence d'oracle. L'oracle phase 38 n'est PAS élargi.

Référence : PLAN.md phase 43, D43a-D43e ; ETAT.md décision S5 (D-commune-strict).
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import load_communes, load_noms, load_prenoms, load_voies
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "acceptance-gazetteer-corpus"

# --- Liste figée des mots courants -> phrase ordinaire (D43c, D43e). ---
#
# Figée au commit : le commit GREEN ne la modifie pas (anti-tricherie). Les 3
# faux positifs concrets de la recette 0.1.4 sont imposés (pierre, douze,
# champ). Chaque phrase emploie le mot dans son sens courant, en prose
# administrative ordinaire, sans verbe d'adresse ni type de voie ni code
# postal (pas d'indice contextuel).
MOTS_COURANTS: dict[str, str] = {
    "pierre": "La pierre angulaire du dispositif a été vérifiée.",
    "douze": "Le contrat court sur douze mois après la rupture.",
    "champ": "Le champ de la mission couvre l'audit complet du périmètre.",
    "fontaine": "La fontaine de la place a été restaurée l'an dernier.",
    "jardin": "Le jardin de la maison est riche en tilleuls.",
    "tour": "La tour de contrôle a autorisé l'atterrissage.",
    "roche": "La roche calcaire se désagrège sous la pluie.",
    "vert": "Le code vert signale une situation normale.",
    "blanc": "Le blanc d'oeuf doit être battu en neige.",
    "grand": "Le grand hall accueille les visiteurs.",
    "croix": "La croix de la chapelle se dresse sur la colline.",
    "bois": "Le bois de la charpente est sain.",
    "pont": "Le pont de la rivière sera fermé demain.",
    "broc": "Le broc ancien trône sur la cheminée.",
    "val": "Le val de la rivière est couvert de prairies.",
    "champagne": "Le champagne est servi bien frais.",
    "fosse": "La fosse de l'ancienne mine est sécurisée.",
    "gare": "La gare de la ville est en travaux.",
    "mairie": "La mairie du village a publié un arrêté.",
    "place": "La place du marché accueille les producteurs.",
    "rivière": "La rivière a débordé après l'orage.",
    "temple": "Le temple de la vallée domine le paysage.",
    "château": "Le château de la vallée est à l'abandon.",
    "porte": "La porte du fond est restée ouverte.",
    "neuf": "Un appartement neuf est au troisième étage.",
    "fer": "Le fer de la rampe est rouillé.",
    "rouge": "Le rouge du drapeau a pâli.",
    "col": "Le col de la chemise est bien repassé.",
    "baron": "Le baron de la légende est revenu au village.",
    "verger": "Le verger de la ferme est plein de pommes.",
    "noyer": "Le noyer du jardin a plus de cent ans.",
    "chêne": "Le chêne de la ferme a été frappé par la foudre.",
    "tilleul": "Le tilleul de la cour embaume la maison.",
    "puits": "Le puits du village est asséché.",
    "aigle": "La silhouette de l'aigle s'est éloignée dans les nuages.",
    "faucon": "Le faucon du clocher est surveillé de près.",
    "eu": "J'ai eu la confirmation du service hier.",
    "madeleine": "La madeleine de la boutique est encore tiède.",
    "aube": "L'aube se lève sur le village.",
    "chemin": "Ce chemin est long et boueux en hiver.",
    "route": "La route du col est longue.",
    "rue": "La rue du village est bordée de tilleuls.",
    "moulin": "Le moulin de la crête ne tourne plus.",
    "vigne": "La vigne du coteau est taillée au printemps.",
    "pomme": "La pomme du verger est mûre.",
    "poire": "La poire du dessert est juteuse.",
    "cerise": "La cerise de la tarte est bien sucrée.",
    "noix": "La noix du gâteau apporte une touche.",
    "orme": "L'orme de la place est centenaire.",
    "saule": "Le saule de la route ombrage le banc.",
    "sapin": "Le sapin de la cour est bien droit.",
    "buis": "Le buis de la haie est taillé au cordeau.",
    "laurier": "Le laurier de la sauce parfume le plat.",
    "thym": "Le thym de la salade apporte une note.",
    "lavande": "La lavande de la colline est en fleur.",
    "menthe": "La menthe du pot est fraîche.",
    "sable": "Le sable de la dune est doré.",
    "dune": "La dune de la plage avance lentement.",
    "barrage": "Le barrage de la rivière est désaffecté.",
    "digue": "La digue du port a résisté à la houle.",
    "plage": "La plage du camping est déserte.",
    "orage": "L'orage de la nuit a coupé le courant.",
    "vent": "Le vent du nord a forci.",
    "neige": "La neige de la nuit a recouvert le jardin.",
    "gel": "Le gel de l'hiver a durci le chemin.",
    "ombre": "L'ombre du mur couvre la table.",
    "lumiere": "La lumière de la salle est tamisée.",
    "brise": "La brise de la berge rafraîchit la soirée.",
    "mirage": "Le mirage de la vallée a faussé la lecture.",
    "onde": "L'onde de la rivière se déroule lentement.",
    "flot": "Le flot de la foule a grossi le boulevard.",
    "loup": "Le loup de la forêt rôde la nuit.",
    "renard": "Le renard du bocage a croisé le chemin.",
    "chat": "Le chat de la voisine est resté dehors.",
    "ours": "L'ours de la légende est une création.",
    "cerf": "Le cerf de la clairière s'est arrêté.",
    "sanglier": "Le sanglier du taillis a traversé le champ.",
    "fort": "Le fort de la presqu'île est désaffecté.",
    "saint": "Le saint du village est fêté en juin.",
    "rond": "Le rond de la serviette est en argent.",
}

# Les 3 faux positifs concrets de la recette 0.1.4, imposés par D43c.
FAUX_POSITIFS_RECETTE: tuple[str, str, str] = (
    "La pierre angulaire du dispositif a été vérifiée.",
    "Le contrat court sur douze mois après la rupture.",
    "Le champ de la mission couvre l'audit complet du périmètre.",
)

# Toponymes capitalisés du corpus phase 38 (les 8 phrases « Toponymes / noms
# de lieux » de test_recall_precision_corpus.py). Disjointness D43b / critère 7.
TOPONYMES_CORPUS_38: tuple[str, ...] = (
    "Le train part de Lyon à huit heures.",
    "La réunion se tient à Paris.",
    "Nous avons visité Bordeaux l'été dernier.",
    "Le colis transite par Marseille.",
    "La conférence a lieu à Lille.",
    "Le siège social est situé à Nantes.",
    "La route nationale passe par Tours.",
    "Le festival se déroule à Avignon.",
)

_GAZETTEERS = (load_communes(), load_voies(), load_noms(), load_prenoms())

# Types des 4 gazetteers : un span de l'un de ces types rend la phrase non
# préservée (oracle D43b).
_TYPES_GAZETTEER = (
    EntityType.PRENOM,
    EntityType.PATRONYME,
    EntityType.COMMUNE,
    EntityType.VOIE,
)


def _corpus_phrases() -> tuple[str, ...]:
    """Corpus négatif auto-généré (D43a) : phrases des mots trouvés dans au
    moins un gazetteer, recalculé à l'exécution (rien de figé en dur)."""
    return tuple(
        phrase for mot, phrase in MOTS_COURANTS.items() if any(mot in g for g in _GAZETTEERS)
    )


def _mots_dans(gazetteer_index: int) -> list[str]:
    return [mot for mot in MOTS_COURANTS if mot in _GAZETTEERS[gazetteer_index]]


@pytest.fixture
def vault(tmp_path):
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    yield v
    v.close()


class TestCouvertureIntersection:
    """D43c (anti-tricherie) : la liste est figée, l'intersection n'est pas
    vide, la couverture est réelle (le corpus est dérivé des gazetteers)."""

    def test_couverture_minimale(self) -> None:
        corpus = _corpus_phrases()
        communes = _mots_dans(0)
        voies = _mots_dans(1)
        print(
            f"couverture: {len(corpus)} phrases (intersection), "
            f"{len(communes)} mots dans communes, {len(voies)} mots dans voies, "
            f"{len(_mots_dans(2))} dans noms, {len(_mots_dans(3))} dans prénoms"
        )
        assert len(MOTS_COURANTS) >= 50, "liste : >= 50 mots français courants"
        assert len(corpus) >= 30, f"corpus : {len(corpus)} phrases < 30"
        assert len(communes) >= 20, f"communes : {len(communes)} mots < 20"
        assert len(voies) >= 10, f"voies : {len(voies)} mots < 10"

    def test_faux_positifs_recette_presents(self) -> None:
        """Les 3 faux positifs concrets de la recette sont dans le corpus."""
        corpus = set(_corpus_phrases())
        for phrase in FAUX_POSITIFS_RECETTE:
            assert phrase in corpus, f"faux positif imposé absent du corpus : {phrase!r}"


class TestNonDivergenceCorpus38:
    """D43b / critère 7 : les phrases du corpus 43 sont disjointes des
    toponymes capitalisés du corpus phase 38 (pas de recouvrement qui masquerait
    une divergence d'oracle)."""

    def test_phrases_disjointes_corpus_38(self) -> None:
        corpus = set(_corpus_phrases())
        assert not (corpus & set(TOPONYMES_CORPUS_38)), (
            "corpus 43 en intersection avec les toponymes capitalisés du corpus 38"
        )


class TestPrecisionCorpusGazetteer:
    """Précision : aucune phrase ordinaire ne doit produire un span PRENOM,
    PATRONYME, COMMUNE ou VOIE (oracle D43b, 4 types gazetteer)."""

    @pytest.mark.parametrize("phrase", _corpus_phrases())
    def test_aucun_span_type_gazetteer(self, vault, phrase: str) -> None:
        m = vault.mask(phrase)
        problemes = [
            (s.type.value, round(s.confidence, 2), s.start)
            for s in m.entities
            if s.type in _TYPES_GAZETTEER
        ]
        assert not problemes, f"faux positif dans {phrase!r}: {problemes}"

    def test_precision_globale_sup_egal_95(self, vault) -> None:
        """D43b : seuil global de précision >= 0.95, affiché en valeur continue."""
        total = 0
        preservees = 0
        rouges: list[str] = []
        for phrase in _corpus_phrases():
            total += 1
            m = vault.mask(phrase)
            if not any(s.type in _TYPES_GAZETTEER for s in m.entities):
                preservees += 1
            else:
                rouges.append(phrase)
        precision = preservees / total
        print(
            f"precision={precision:.3f} ({preservees}/{total} préservées, seuil precision >= 0.95)"
        )
        if rouges:
            print("phrases rouges :")
            for r in rouges:
                print("  ", r)
        assert precision >= 0.95, f"precision={precision:.3f} < 0.95 sur {total} phrases"
