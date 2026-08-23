## 0.1.5 (2026-08-23)

Correctifs recette 0.1.4 (phases 42-43) : précision COMMUNE/VOIE par indices
stricts (D42c, D-commune-strict S5), corpus négatif régénéré par intersection
mots courants x gazetteers, généralisation de la règle de confiance (aucun
span < 0.8 en `permissive` sans indice contextuel, quel que soit le type,
défaut SAFE). Aucun changement d'API publique. Limitation annoncée : les
communes sans indice d'adresse fort (prose, en-têtes de lettre) ne sont pas
masquées en `permissive`. Tag v0.1.5 et publication PyPI réservés à
l'orchestrateur.

### D42 (phase 42) - Précision COMMUNE/VOIE par indices stricts

- **Avant** : une commune ou une voie pouvait être émise sur la seule
  présence dans le gazetteer, sans indice contextuel d'adresse ; des
  toponymes de prose (« Je vais à Paris ») pouvaient être masqués à tort.
- **Après** : indices stricts exigés (D42c, D-commune-strict S5) : pour
  COMMUNE, un verbe d'adresse (`domicilié à`, `habite à`, `réside à`) ou un
  code postal adjacent ; pour VOIE, un type de voie (rue, avenue,
  boulevard...) accompagné d'un numéro. Le mode `observe` continue de montrer
  ces candidats sans les émettre ; `strict` les lève.
- Contre-exemples D39d obsoletes (phases 34-36) mis à jour pour refléter la
  règle stricte (phase 42) : les communes en prose sans indice d'adresse
  fort sont préservées.

### D43 (phase 43) - Corpus négatif régénéré

- Le corpus négatif est désormais auto-généré par intersection des mots
  courants avec les 4 gazetteers (prénoms, patronymes, communes, voies) :
  précision 1.000, et il se régénère automatiquement quand les gazetteers
  changent (script `scripts/build_gazetteers.py`), au lieu d'une liste
  figée maintenue à la main.

### Règle de confiance généralisée (phase 42)

- **Avant** : le seuil `WEAK_CONFIDENCE_THRESHOLD = 0.8` ne s'appliquait
  qu'à certains types (PATRONYME, PRENOM) ; des spans à confiance plus basse
  d'autres types pouvaient encore être émis en `permissive` sans indice
  contextuel.
- **Après** : aucun span à confiance < 0.8 n'est émis en `permissive` sans
  indice contextuel, quel que soit le type de la span. Le mode par défaut
  SAFE filtre ces candidats par défaut ; `observe` les montre, `strict` les
  lève avec erreur.

### Limitation annoncée - Communes sans indice d'adresse fort

- En `permissive`, les communes sans indice d'adresse fort ne sont pas
  masquées : toponymes de prose (« Je vais à Paris ») et en-têtes de lettre
  (« Paris, le 23 août ») sont préservés.
- Un utilisateur soucieux de masquer la commune de résidence emploie le mode
  `strict` ou fournit un verbe d'adresse explicite (`domicilié à`,
  `habite à`), ce qui lève l'indice requis et permet le masquage.

## 0.1.4 (2026-08-23)

Correctifs recette 0.1.3 (phases 38-40) : rappel patronymes >= 98 % en
permissive (R3), arbitrage prénom/commune avec PRENOM gagnant si patronyme
adjacent (R4), résidu round-trip résolu (B2), double corpus de non-régression
en CI. Aucun changement d'API publique ; le mode `observe` peut afficher plus
de candidats qu'avant (le jeu de spans détectés s'élargit via D38a/D38c,
contrat observe/strict inchangé). Tag v0.1.4 et publication PyPI réservés à
l'orchestrateur.

### R3 (phase 38) — Rappel patronymes >= 98 % en permissive

- **Avant** : des patronymes nus isolés en milieu de phrase pouvaient ne pas
  être émis en `permissive` (rappel sous la cible), malgré un filtre de
  candidats nus déjà restreint introduit en 0.1.3.
- **Après** : interprétation littérale D38b — un nom nu isolé en milieu de
  phrase est masqué ; les faux positifs des zones de début sont contenus par
  le contexte. Rappel mesuré sur double corpus : 1.000 (56/56 patronymes,
  11 contextes), précision 1.000 (54/54 phrases négatives préservées).
- Double corpus de non-régression (positif/negatif) ajouté en CI
  (`tests/acceptance/test_recall_precision_corpus.py`, 108 tests).

### R4 (phase 39) — Arbitrage prénom/commune

- **Avant** : une forme type « Marie Lefebvre » pouvait être classée commune
  (« Marie »), car le gazetteer communes (paris, marie...) gagnait par ordre
  de résolution.
- **Après** : arbitrage explicite — PRENOM gagne quand un patronyme adjacent
  est détecté (« Marie Lefebvre », « Mme Marie Lefebvre », « Présents : Marie
  Lefebvre »), avec invariants F3 tenus (`span.rule_id == mask-prenom`) et
  contre-exemples D39d préservés (« Je vais à Paris. », « à Marie »).

### B2 (phase 40) — Résidu round-trip résolu

- **Cause identifiée** : l'AC span hits propageait une longueur de motif
  erronée sur le span de sortie quand le substitut composite (multi-mots)
  réécrivait le contexte suivant le nom.
- **Corrigé** : la longueur du motif est calculée par output span ; le
  résidu round-trip 4/2 000 de la recette est résolu — 0 échec sur
  5 000 (test `test_roundtrip_5000.py`), plus un test de non-régression
  dédié au substitut composite (le « m » de fin n'est plus avalé).
- Compte de tests : 1246 passed (1108 en 0.1.3 base, 1246 après phase 40).

## 0.1.3 (2026-08-22)

Correctifs recette 0.1.2 (phases 34-36) : précision patronymes/prénoms (R1),
premier mask() < 3 s (R2), filet global anti-fuite + détection patronymes
composés (S1), restitution casse des noms composés (B2). Aucun changement
d'API publique ; tag v0.1.3 et publication PyPI réservés à l'orchestrateur.

### R1 (phase 34) — Précision patronymes/prénoms

Le premier mot de chaque phrase n'est plus masqué sans contexte.

- **Avant** : tout candidat gazetteer (noms ou prénoms) émettait un span,
  y compris en initiale de phrase sans déclencheur (« Le contrat prend
  effet... » masquait « Le », « Paul est arrivé hier. » masquait « Paul »).
- **Après** : liste d'exclusion `EXCLUDED_NOMS` (mots-outils + acronymes :
  `le, la, les, il, elle, nous, vous, cette, ce, ces, des, pour, sur, dans,
  par, avec, sans, nir, siret, siren, iban, tva, rib`) appliquée en filtre
  global sur tous les candidats PATRONYME ; candidats nus (PATRONYME et
  PRENOM, sans déclencheur, confiance < 0.8) non émis en `permissive`
  (conservés en `strict` pour lever et en `observe` pour montrer).
- Précision patronymes en contexte déclenché restaurée : le premier mot des
  phrases sans donnée personnelle est préservé.

### R2 (phase 35) — Premier mask() < 3 s

- **Avant** : permutation Feistel matérialisée (`forward = [perm.encrypt(i)
  for i in range(n)]`, O(N) sur 879 273 noms) + reconstruction de
  `hmac.new()` à chaque tour → premier mask() 52 s (cible PRD §10 < 30 s
  non tenue).
- **Après** : permutation paresseuse calculable valeur par valeur (O(1) par
  nom) + objet HMAC unique préparé puis `.copy()` par tour (blake2b
  interdit, images figées 0.1.2 inchangées → migration des registres sûre).
  Premier mask() 52 s → < 3 s (cible PRD §10 tenue).

### S1 (phase 35) — Filet global anti-fuite + patronymes composés

- Filet de sûreté **global** appliqué après la boucle de substitution sur la
  liste `substitutions` (vérifie `substitute != text[start:end]` pour chaque
  entrée), couvrant tous les chemins (CP, FPE, gazetteer, context-capture).
- En `permissive` : sondage borné (max 1000 tentatives) jusqu'à un substitut
  non-collisionnant ; `UserWarning` seulement si la fuite reste avérée après
  sondage. En `strict` : `UnresolvedSpanError` dans tous les cas.
- Détection multi-mots des patronymes composés (jusqu'à 3 mots) via le
  préfiltre `first_words` (O(1) par premier mot). 0 patronyme composé de la
  recette (« ALTOUBAH MIANGOGO », « MIKISSI NLEMVO », « MAYEYA N'YALA »,
  « ENGOUTA MAMBINDA », « TEJONA JOKUNG », « BASEKAYI KABUNDI », « ADEBUJI
  ONIKOYI », « KUSONI KAYILU ») ne ressort identique.

### B2 (phase 36) — Restitution casse des noms composés

- **Cause identifiée** : `title()` global capitalisait les particules
  (« de » → « De » dans « DUPONT DE LIGONNÈS ») et l'article élidé (« l' » →
  « L' »).
- **Corrigé** : `apply_case` encode la casse par segment (`T-l-T` / `l'T`)
  au lieu de `title()` global. Round-trip résidu 0,25 % (5/2 000) → 0.
- Compte de tests : 1129 passed (949 en 0.1.2 base, 1108 après phase 34,
  1112 après phase 35).

## 0.1.2 (2026-08-22)

Correction du défaut `__version__` : la 0.1.1 a été publiée sur PyPI avec
`anonyfy.__version__ == "0.1.0"` (oubli du bump dans
`src/anonyfy/__init__.py` lors de la phase 33). Alignement de
`__version__` sur la version du paquet déclarée dans `pyproject.toml`.
Aucun changement fonctionnel ; 0.1.1 reste sur PyPI (yankable plus tard).

## 0.1.1 (2026-08-22)

Correctifs recette v0.1.0 : séparateurs SIRET/SIREN (B1), points fixes
détecteur (S1), round-trip vault (B2), gazetteers INSEE complets (S2), typage
patronyme (S3), code postal/commune (S4), exclusion data/raw (M3), performance
mask() (M4) et description PyPI (M5).

### Phase 32 — M4: Performance mask()

Latence `mask()` sur 10 000 caractères (PRD §6). Cible stricte 50 ms.

- **Avant**: 249 ms (texte dense ~250 SIRET, steady-state, mono-thread).
- **Après**: ~62-66 ms (best), médiane ~86 ms (variabilité charge CI).
- **Cible stricte 50 ms inatteignable**: le FPE FF3-1 (lib `ff3` +
  `pycryptodome`) chiffre ~250 SIRET uniques (~30 ms non réductibles sans
  changer d'algorithme, hors périmètre). Arbitrage S5: seuil assoupli.
- **Seuil retenu (texte dense)**: `< 100 ms` (marge CI réaliste, non
  tautologique). Texte peu dense: `< 50 ms` (atteint, conservé).

#### Optimisations (profilage `cProfile` d'abord, une à la fois)

1. **Interval tree bisect** dans `resolve_overlaps` (O(n²) → O(n log n)):
   remplaça `any(_overlaps(span, kept) for kept in selected)` (17 M appels
   genexpr) par liste triée + `bisect`. 249 ms → 96 ms.
2. **Bisect + precasefold** dans `triggers`/`places`: `_overlaps_trigger` et
   `_near_trigger` O(n×m) → O(log n) via `bisect` + `max_te_prefix`; tokens
   pre-casefold une fois par `detect()`. 96 ms → 88 ms.
3. **Préfiltre `first_words`** au `Gazetteer`: set des premiers mots casefold
   pour court-circuiter `_phrase_matches` quand le premier token ne peut
   démarrer aucune entrée. 88 ms → 72 ms.
4. **Luhn par paires** (`luhn_checksum`): table précalculée de contributions
   par paire de chiffres (moitié d'itérations, `ord()` au lieu de `int()`).
   `luhn_check_digit`: calcul direct en un passage au lieu de 10 candidats.
5. **Cache FF3Cipher** (`lru_cache`): `FF3Cipher.__init__` reconstruisait un
   contexte AES à chaque SIRET (5260 constructions/mask); le cipher étant
   stateless (ECB), un seul suffit par (clé, tweak). 70 ms → 56 ms.

#### Tests

- `tests/acceptance/test_latency.py::test_mask_10k_chars_under_50ms` (texte
  peu dense, < 50 ms, passe).
- `tests/acceptance/test_latency.py::test_mask_10k_dense_under_50ms` (texte
  dense ~250 SIRET, < 100 ms, escalade S5 documentée).

## 0.1.0

Première version publiable. Pseudonymisation réversible et déterministe
des données personnelles françaises, avant transmission à un modèle de
langage. Livraison des jalons M0 à M4 du plan v1.2 (phases 01 à 19).

### Ajouté

- **Phase 01** — Squelette du paquet Python (`pyproject.toml`, `uv`,
  `src/anonyfy/` vide, licence Apache-2.0, `.python-version` pin 3.11).
- **Phase 02** — CI GitHub Actions (matrice 3.11 / 3.12 / 3.13, ruff,
  pytest, test canari).
- **Phase 03** — README initial, ADR 0001 (FPE FF3-1, décisions crypto),
  ADR 0002 (jamais de service hébergé), cadrage juridique
  (`docs/JURIDIQUE.md`).
- **Phase 04** — Types de base (`Span`, `MaskedText`, `Entity`, `Rule`,
  `AuditEntry`) et invariants testables (`types.py`, `invariants.py`).
- **Phase 05** — Validateurs arithmétiques (SIREN, SIRET, NIR, IBAN, TVA,
  carte bancaire) par regex + contrôle (Luhn, mod 97).
- **Phase 06** — Validateurs de format (téléphone FR, plaque SIV, date,
  email, référence de dossier configurable).
- **Phase 07** — FPE FF3-1 sur les grands domaines (NIR, SIREN, SIRET,
  IBAN, TVA, CB, téléphone) via `ff3` isolé derrière `surrogate/fpe.py`,
  recalcul des clés de contrôle, vecteurs NIST avec clé non nulle (D6).
- **Phase 10** — Registre de scope SQLite (`schema_version`, écriture
  atomique, verrou par scope, test de concurrence, latence 50 000
  entrées, jamais de clair stocké).
- **Phase 10b** — Automate Aho-Corasick + dictionnaire de variantes
  normalisées (espaces, ponctuation, casses, groupes de chiffres,
  « M. Leroy » vs « Marc Leroy ») pour retrouver les substituts émis dans
  la réponse du modèle, y compris reformatée (D7).
- **Phase 08** — API publique `Vault.mask` / `Vault.unmask` aller-retour
  sur identifiants structurés à grand domaine, avec registre (invariant 4)
  et intégration Aho-Corasick (test d'intrusion: un SIRET jamais émis
  n'est pas déchiffré).
- **Phase 09** — Gazetteers embarqués figés (source, version, SHA-256):
  prénoms INSEE, patronymes SIRENE data.gouv.fr (D19), communes COG 2026,
  voies BAN; empreinte de version vérifiée au unmask
  (`GazetteerVersionMismatch`); < 20 Mo.
- **Phase 11** — Substituts gazetteer par sélection déterministe HMAC,
  préservation des attributs (genre pour prénoms, département pour
  communes).
- **Phase 12** — Déclencheurs contextuels (`M.`, `Mme`, `Maître`,
  `né(e) le`, `demeurant`) qui élèvent la confiance d'un candidat
  gazetteer.
- **Phase 13** — Arbitrage complet (spécificité > longueur > priorité,
  journalisé) et extension de `mask`/`unmask` aux patronymes, prénoms,
  communes, voies, dates (bucket de mois D8), emails (local-part NFKC
  D9), plaque SIV et référence de dossier (mécanisme registre D2).
  Permutation keyée Feistel pour les petits domaines non-FPE (D22),
  points fixes détectés (D23), préservation de la casse par flag registre
  (D24), cohérence des offsets `.entities` (D15), test de non-collision
  sur 5 000 patronymes.
- **Phase 14** — Journal d'audit (`audit.py`): JSON lines, empreinte
  HMAC-SHA-256(key, texte) (D3), méta uniquement (jamais le texte ni les
  substituts, D10).
- **Phase 15** — Rapport `Vault.report()`: synthèse lisible par un DPO
  (types rencontrés, volumes, règles actives, version du gazetteer).
- **Phase 16** — CLI `anonyfy scan|mask|unmask` (stdlib `argparse`),
  sécurité de la clé (`--key-file` refuse mode groupe/autre,
  avertissement si `ANONYFY_KEY` héritée), registre persistant,
  `docs/MENACE.md` (modèle de menace sur la gestion de clé, D11).
- **Phase 17** — Mode observation (`observe=True`: détecte, journalise,
  ne modifie rien, PRD F7) et politique de fermeture `permissive` /
  `strict` (seuil `WEAK_CONFIDENCE_THRESHOLD = 0.8`, PRD F8).
- **Phase 18** — `mask_json` / `unmask_json`: parcours récursif de
  l'arbre JSON, ne touche qu'aux feuilles chaîne, jamais les clés ni
  `function.name`; politique d'exemption par chemin (`$.tools[*].function.name`).
  Préparation au proxy v2; `mask_json` est une **primitive, pas un proxy**
  (OBJ-025).
- **Phase 19** — Corpus de test (synthétique de non-régression + corpus
  réel annoté ou documentation d'indisponibilité, D12), automatisation des
  9 critères d'acceptation v1, test de débit FPE informatif (D14), test
  d'intégration avec clé aléatoire (D6), corpus email (D9).

- **Phase 27** — Gazetteers INSEE complets (S2): noms 879 273 entrées
  (source: `patronymes.csv` data.gouv.fr), prénoms 36 170 entrées (source:
  `nat2021_csv.zip` INSEE). Câblage de `check_gazetteer_version` dans
  `ScopeRegistry.__init__` (OBJ-REC-103, schéma v4, migration
  ALTER TABLE, `GazetteerVersionMismatch` à la rouverture si l'empreinte
  diffère). Chargement paresseux par type (OBJ-REC-107: ciphers construits
  au premier usage, dictionnaire `_pos` remplacé par tri + `bisect`).
  Filtrage Aho-Corasick par frontière de mot et couverture (corrige le
  round-trip des patronymes composés exposé par le gazetteer complet).

### Migration

- **Phase 27** — Les registres v0.1.0 antérieurs à la phase 27 sont
  **incompatibles** avec le nouveau gazetteer. La permutation keyée change
  avec la taille du gazetteer (879k noms au lieu de 5k), ce qui modifie
  tous les substituts. À la première ouverture d'un registre existant,
  `GazetteerVersionMismatch` est levée. Supprimer les registres obsolètes
  (`rm ~/.anonyfy/registries/*.db`) ou exporter les données avant migration.

### Sécurité

- Quatre invariants garantis par construction et testés: le clair ne
  franchit jamais la frontière (invariant 1), déterminisme scopé
  (invariant 2), injectivité dans le scope (invariant 3), rien n'est
  démasqué qui n'ait été masqué (invariant 4).
- Audit HMAC-SHA-256 keyé (D3); logging méta uniquement, jamais le texte
  ni les substituts (D10).
- `ff3` isolé derrière `surrogate/fpe.py`; plan de remplacement déclenché
  par critères (ADR 0001 §3, D13).
- Gazetteer figé source+version+SHA-256 (D5); `GazetteerVersionMismatch`
  au unmask si l'empreinte diffère.

### Limites documentées (v1)

- Ce n'est pas de l'anonymisation au sens RGPD (pseudonymisation
  réversible). Voir `docs/JURIDIQUE.md`.
- Ré-identification par contexte (PRD §8 point 1): un substitut peut
  ré-identifier si le contexte autour est unique.
- Dictionnaire de code (§8 point 2): un mapping déterministe est un code
  book; mitigation par clé secrète et sel par scope.
- Compromission de la clé (§8 point 3): la clé permet de tout inverser.
- FPE sur petits domaines (§8 point 4): bijectivité mais pas derangement
  (points fixes D23, probabilité ~1/N, détectés et alertés).
- Date par bucket de mois (D8): la précision jour n'est pas préservée;
  ré-identifiable par contexte.
- Rotation de clé **hors périmètre v1** (T1, OBJ-009/024): reportée à v2
  (exigerait un registre stockant du clair, interdit par invariant 1).
- Cohérence inter-type SIREN/SIRET/TVA non garantie (OBJ-008): FPE
  indépendant par type.
- Collision inter-type PRENOM/PATRONYME (D26): `RegistryError` rare en
  production; workaround re-key, solution v2 sondage registre + offset.
- `mask_json` est une primitive, pas un proxy (OBJ-025): le proxy
  compatible OpenAI est prévu en v2.

### Outils

- `uv` project, `pyproject.toml`, `uv.lock`, Python >= 3.11.
- Dépendance runtime: `ff3` v1.0.3 (Apache-2.0) + transitive `pycryptodome`.
- CI: GitHub Actions, matrice 3.11 / 3.12 / 3.13, ruff + pytest.
- CLI: `anonyfy scan|mask|unmask` (stdlib `argparse`, zéro dépendance
  supplémentaire).

### Documentation

- README final (installation, tutoriel 30 s, limites §8, modèle de
  menace, `mask_json` primitive pas proxy).
- `docs/TUTORIAL.md` — guide d'intégration détaillé.
- `docs/JURIDIQUE.md` — cadrage juridique (pseudonymisation vs
  anonymisation, *EDPS c. CRU*).
- `docs/MENACE.md` — modèle de menace (gestion de clé + 4 menaces §8).
- `docs/ADR/0001-fpe-ff3.md` — FPE FF3-1, registre, décisions crypto.
- `docs/ADR/0002-pas-de-service-heberge.md` — jamais de service hébergé.
- `docs/ADR/0003-permutation-feistel-petits-domaines.md` — permutation
  keyée pour les petits domaines non-FPE (D22).
- `CONTRIBUTING.md` — guide de contribution (TDD, Olgenius, branches,
  tests, sécurité).