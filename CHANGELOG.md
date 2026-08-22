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