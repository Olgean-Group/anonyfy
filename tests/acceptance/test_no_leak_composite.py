"""Phase 35 — S1 (D35e/D35f/D35g/D35h, OBJ-002): aucune fuite de patronymes.

La recette S1: 12 patronymes composes (deux mots) ressortaient identiques a
l'original (0,60 % des 2 000 testes). Le span compose etait detecte en tokens
simples (context-capture) mais aucun token seul n'est dans le gazetteer noms:
``GazetteerCipher.encrypt`` renvoyait ``None``, la boucle de substitution
sautait le span et le texte ressortait inchange, SANS signal (l'avertissement
``UserWarning: Point fixe permutation`` de la 0.1.0 avait disparu).

Correctif phase 35:
  - D35e: detection multi-mots des patronymes composes contre le gazetteer noms
    (modele ``_phrase_matches`` de places.py, prefilter restreint aux entrees
    multi-mots, ``_MAX_WORDS`` borne a 3). Le span compose est un ``Span``
    unique couvrant les mots, masquable par le cipher (l'entree composee EST
    dans le gazetteer).
  - D35f: filet de surete GLOBAL, applique apres la boucle de substitution sur
    la liste ``substitutions`` (substitut == clair ?), couvrant tous les chemins
    (CP, FPE, gazetteer, context-capture).
  - D35g: le ``UserWarning`` n'est emis qu'apres le sondage, uniquement si le
    substitut final reste == clair (fuite averee non resolue).
  - D35h: sondage deterministe borne (max 1000 tentatives) en permissive; en
    strict, lever ``UnresolvedSpanError`` (teste dans test_policy.py).

Le test CP point fixe (D35f-01, OBJ-002): un CODE_POSTAL pre-enregistre avec
son propre clair comme substitut (enregistre de force via ``register_fpe``,
chemin qu'aucun mecanisme de sondage ne peut plus defaire) provoque le dernier
recours: clair laisse en place + ``UserWarning``. Sans le filet global, ce cas
sortirait identique sans signal.

Reference: PLAN.md phase 35, criteres d'acceptation 3 et 4.
"""

from __future__ import annotations

import pytest

from anonyfy import Vault
from anonyfy.types import EntityType

_KEY = b"0" * 16
_SCOPE = "acceptance-no-leak-composite"

#: Compose de la recette S1 (ceux qui fuyaient en 0.1.2). Chaque token simple
#: est absent du gazetteer nomes (uniquement l'entree multi-mots existe).
_COMPOSES_RECETTE = (
    "ALTOUBAH MIANGOGO",
    "MIKISSI NLEMVO",
    "MAYEYA N'YALA",
    "ENGOUTA MAMBINDA",
    "TEJONA JOKUNG",
    "BASEKAYI KABUNDI",
    "ADEBUJI ONIKOYI",
    "KUSONI KAYILU",
)


def _patronymes_composes(limit: int) -> list[str]:
    """Patronymes multi-token du gazetteer (les 8 de la recette en tete)."""
    from anonyfy.detect.gazetteers.loader import load_noms

    composes = [e.name for e in load_noms() if " " in e.name]
    recette = [n for n in _COMPOSES_RECETTE if n not in composes]
    return (recette + composes)[:limit]


@pytest.fixture(scope="module")
def noms() -> list[str]:
    return _patronymes_composes(300)


@pytest.fixture(scope="module")
def vault(tmp_path_factory) -> Vault:
    v = Vault(
        key=_KEY,
        scope=_SCOPE,
        registry_path=str(tmp_path_factory.mktemp("no-leak") / "reg.db"),
    )
    yield v
    v.close()


class TestCompositesNonFuite:
    """Aucun patronyme compose ne ressort identique a l'original (S1)."""

    @pytest.mark.parametrize("nom", _COMPOSES_RECETTE)
    def test_compose_recette_non_fuite(self, vault, nom: str) -> None:
        m = vault.mask(f"M. {nom}")
        assert nom.casefold() not in m.text.casefold(), (
            f"patronyme compose {nom!r} resorti identique: {m.text!r}"
        )

    def test_echantillon_composes_non_fuite(self, vault, noms) -> None:
        """Aucun des composés de l'echantillon ne ressort identique."""
        fuites = []
        for nom in noms:
            m = vault.mask(f"M. {nom}")
            if nom.casefold() in m.text.casefold():
                fuites.append(nom)
                if len(fuites) >= 10:
                    break
        assert not fuites, f"{len(fuites)} patronymes composes sortis identiques"

    def test_compose_single_token_reste_masque(self, vault) -> None:
        """Non-regression : un patronyme simple reste masque (D34e)."""
        m = vault.mask("M. Dupont")
        assert "Dupont" not in m.text


class TestCpPointFixe:
    """D35f : le chemin CODE_POSTAL est couvert par le filet global (OBJ-002).

    Un CP dont le substitut enregistre de force == clair (point fixe que le
    sondage ne peut pas defaire) ressort a l'identique avec un ``UserWarning``
    (jamais en silence).
    """

    def test_cp_point_fixe_emission_warning(self, tmp_path) -> None:
        v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
        try:
            # Enregistrer le point fixe (substitut == clair) comme une entree
            # deja persistee d'une version cassee; plus rien ne peut le defaire.
            # Casse canonique EntityType.CODE_POSTAL.value (le mask enregistre
            # les entites en majuscules; l'idempotence du registre depend du
            # HMAC scope||type||clair, sensible a la casse du type).
            v._registry.register_fpe(
                EntityType.CODE_POSTAL.value, "16000", surrogate="16000", clear_index=16000
            )
            with pytest.warns(UserWarning):
                m = v.mask("Je demeure à 16000")
            # Dernier recours : le clair reste, mais le warning est emis.
            assert "16000" in m.text
        finally:
            v.close()


class TestComposeInconnu:
    """D35e: un compose inconnu du gazetteer (tokens absents) n'est pas fuite.

    Le span compose n'est pas emis (pas dans le gazetteer) mais les tokens
    simples restent captures par le trigger (context-capture 0.8) : ils ne
    sont pas masquables (encrypt None). En permissive, le texte ressort sans
    span compose -> les tokens seuls sont laisses tels quels (choix D22(ii),
    non masquables). Ce test garantit que le nom inconnu ne produit ni
    exception ni span compose fantome (le comportement actuel de la phase 34
    est preserve).
    """

    def test_compose_inconnu_reste_clair_sans_erreur(self, vault) -> None:
        m = vault.mask("M. Xyzzqq Zzqqxx")
        assert m.text == "M. Xyzzqq Zzqqxx"
