"""Phase 35 — R2 (D35c, OBJ-008): premier mask() < 30 s (permutation paresseuse).

La recette R2: le premier ``mask()`` prenait 52 s car la permutation du
gazetteer etait materialisee en entier (879k encrypts + 11M hmac.new par tour)
pour masquer un seul nom. La phase 35 rend la permutation paresseuse (O(1) par
nom, aucun tableau forward) et prepare un objet HMAC unique copie par tour
(D35d), sans changer les images (OBJ-003).

Protocole (D35c):
1. ``reset_cache()`` du loader AVANT de creer le Vault pour forcer le
   rechargement du gazetteer (comme un premier usage reel).
2. Construction du Vault (registre SQLite) HORS mesure.
3. Chronometrage au ``perf_counter`` du PREMIER ``vault.mask(...)`` uniquement
   (le chargement du gazetteer fait partie du premier mask, cote fixe d'init;
   le critere PRD §10 porte sur le mask, pas sur la phase d'init).

Reference: PLAN.md phase 35, critere d'acceptation 1.
"""

from __future__ import annotations

import time

from anonyfy import Vault
from anonyfy.detect.gazetteers.loader import reset_cache

_KEY = b"0" * 16
_SCOPE = "acceptance-first-mask-latency"
# Seuil PRD §10 « premier masquage < 30 s » (D35c). La latence avant phase 35
# etait ~52 s sur la machine de la recette (materialisation + hmac par tour).
_THRESHOLD_PRD_S = 30.0
# Seuil de regression : la materialisation de la permutation prenait 17-20 s a
# elle seule sur la machine de dev (O(n) sur 879k entrees). Apres la phase 35
# (calcul paresseux O(1) par nom), le premier mask tombe a ~3 ms. Un seuil a
# 5 s (ordre de grandeur au-dessus du paresseux, 3x sous la materialisation)
# echoue sur le code actuel et confirme la non-regression de la recette R2.
_REGRESSION_S = 5.0


def test_premier_mask_sous_30s(tmp_path) -> None:
    """Premier ``vault.mask`` < 30 s (cible PRD) et < 5 s (non-regression R2)."""
    # Forcer le rechargement du gazetteer (premier usage reel).
    reset_cache()
    # Construction du Vault hors mesure (registre SQLite, ciphers lazies).
    v = Vault(key=_KEY, scope=_SCOPE, registry_path=str(tmp_path / "reg.db"))
    try:
        start = time.perf_counter()
        m = v.mask("M. Dupont")
        elapsed = time.perf_counter() - start
        assert elapsed < _THRESHOLD_PRD_S, (
            f"premier mask {elapsed:.1f} s >= cible PRD {_THRESHOLD_PRD_S} s"
        )
        assert elapsed < _REGRESSION_S, (
            f"premier mask {elapsed:.1f} s >= seuil regression {_REGRESSION_S} s "
            f"(permutation matérialisée en entier ?)"
        )
        # Non-trivialite : le mask a bien reduit « Dupont ».
        assert "Dupont" not in m.text, "le premier mask n'a pas reduit le patronyme"
    finally:
        v.close()
