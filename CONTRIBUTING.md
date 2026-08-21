# Contribuer à anonyfy

Merci de vouloir contribuer. anonyfy est un projet à périmètre Français
(pseudonymisation réversible des données personnelles françaises avant
LLM) et à méthodologie TDD stricte. Les règles ci-dessous sont **obligatoires**.

---

## 1. Méthode de travail: TDD strict

Le projet suit le cycle **rouge -> vert -> refactor** à chaque étape.

- **Rouge**: écrire un test qui échoue et qui prouve l'absence de la
  fonctionnalité attendue. Un test qui ne peut pas échouer pour une vraie
  raison est du bruit et ne sera pas accepté.
- **Vert**: écrire le **minimum de code de production** qui fait passer
  le test. Pas plus.
- **Refactor**: nettoyer le code (tests et production) sans changer le
  comportement; les tests restent verts.

**Interdictions explicites**:

- modifier un test pour le faire passer (si un test est faux, le
  signaler à l'orchestrateur; ne pas le déformer);
- supprimer ou désactiver un test qui gêne;
- écrire une ligne de code de production avant un test qui échoue et la
  justifie;
- inventer une bibliothèque, une API ou une option non vérifiée;
- sortir du périmètre de la phase en cours, même « tant qu'on y est »:
  remonter le besoin découvert à l'orchestrateur plutôt que l'implémenter
  en silence.

### Ce qu'on teste

- logique métier, cas limites, chemins d'erreur, contrats d'interface,
  comportement fonctionnel de bout en bout, et un test de non-régression
  par bug corrigé.

### Ce qu'on ne teste pas

- accesseurs triviaux, code généré, bibliothèques tierces, câblage sans
  logique.

---

## 2. Organisation Olgenius

Le projet est piloté par le plan `.olgenius/PLAN.md` (jalons, phases,
critères d'acceptation exécutables). Les décisions techniques figées sont
dans `.olgenius/DECISIONS.md`. Les objections traitées sont dans
`.olgenius/OBJECTIONS.md` (si présent).

- **planificateur** — établit et corrige le plan (jalons, phases, étapes).
- **orchestrateur** — arbitrage, escalade sécurité (§7), validation.
- **avocat du diable** — challenge le plan pour trouver ce qui casse.
- **dev-tdd** — implémente une phase en TDD strict. **Seul agent autorisé
  à modifier le code source.**
- **qa** — vérifie une phase contre ses critères d'acceptation et
  produit un rapport. **Ne corrige jamais.**

### Rôles d'agents

Si vous contribuez via Olgenius, vous êtes probablement `dev-tdd` ou
`qa`. Respectez votre périmètre: un `dev-tdd` ne modifie pas le plan; un
`qa` ne corrige pas le code (il remonte).

### Machine à états

Une phase = une branche = un passage QA. Aucune phase ne dépend d'une
autre de façon circulaire. L'ordre d'exécution est défini dans
`PLAN.md` (synthèse d'ordonnancement).

---

## 3. Branches et commits

### Branches

- `main` — branche d'intégration, ne jamais committer directement dessus.
- `phase/NN-slug` — une branche par phase (ex. `phase/20-documentation`).
- Créer la branche depuis `main` à jour: `git checkout main && git pull &&
  git checkout -b phase/NN-slug`.

**Ne jamais merger, ne jamais changer de branche, ne jamais toucher à
`main` sans validation explicite de l'orchestrateur.**

### Commits

Format atomique: `phase(NN): <quoi>`.

Exemples valides:

```
phase(20): README final + limites §8 + tutoriel 30s
phase(13): dates bucket de mois (D8) + corpus email (D9)
phase(08): test d'intrusion invariant 4 (SIRET jamais émis)
```

Commits atomiques: un commit par cycle rouge -> vert -> refactor ou par
sous-objectif cohérent. Le `phase(NN):` est obligatoire pour pouvoir
retracer la livraison dans l'historique.

---

## 4. Tests et qualité

### Lancer la suite

```bash
uv run pytest -q                     # 802 passed, 1 skipped, 1 xfailed, 0 failed
uv run ruff check . && uv run ruff format --check .
```

Les deux doivent être verts avant tout commit de code. La documentation
(.md) n'est pas vérifiée par ruff, mais n'introduisez pas de fichier
`.py` non testé.

### Couverture

Pas d'exigence de pourcentage en v1, mais chaque ligne de code de
production doit être justifiée par un test qui échoue sans elle (TDD).
Un test qui ne peut pas échouer pour une vraie raison est du bruit et
sera contesté en revue.

### Déterminisme

Les tests qui s'appuient sur le hasatd doivent être semencés (`random.seed`
ou clé fixe `b'0'*16`). Un test non déterministe est un faux ami. Le
determinisme scopé est un invariant du projet (invariant 2): tout test
qui l'enfreint doit être semencé ou considéré comme faux.

---

## 5. Sécurité — ne jamais fuiter de clair

### Dans les tests

- **Jamais de valeur claire réelle** dans les tests, les fixtures, les
  corpus, ou les commits. Utilisez des valeurs synthétiques (SIRET
  `73282932000033`, NIR `275032917028004`, etc., déjà utilisées dans le
  plan).
- **Jamais de clé réelle** dans le dépôt. Les tests utilisent `b'0'*16`
  pour la logique métier; la validation crypto (D6) utilise des clés non
  nulles **documentées et non secrètes** (vecteurs NIST).
- Les corpus réels annotés (phase 19, D12) sont **hors dépôt** s'ils
  contiennent des données personnelles; un `README.md` documente
  l'indisponibilité et le recours à `anonyfy scan` (mode observation).

### Dans le code

- Invariant 1: le clair ne franchit jamais la frontière. Ni vers un
  service, ni vers un disque, ni vers un journal.
- D10: le logging est méta uniquement (scope, compte par type, règle,
  empreinte HMAC). **Jamais le texte, clair ou substitué.**
- D3: l'empreinte d'audit est HMAC-SHA-256(key, texte), pas SHA-256
  (inversible par dictionnaire).
- La clé est la racine du montage (§8 point 3): jamais dans le dépôt,
  jamais en argument CLI en clair (`--key` est refusé; `ANONYFY_KEY` ou
  `--key-file` mode 0600 seulement). Voir `docs/MENACE.md`.

### Dans les commits

- Ne jamais committer une clé, un secret, ou une donnée personnelle.
- Si un fichier de clé ou de registre est créé localement, ajoutez-le au
  `.gitignore` (le `.gitignore` du projet exclut déjà `*.db`,
  `registries/`, les `.bak` non trackés).

---

## 6. Documentation

La documentation est en Markdown pur, sans générateur de site statique en
v1. Les fichiers de documentation sont:

- `README.md` — présentation, installation, tutoriel 30 s, limites §8,
  mention `mask_json` primitive pas proxy (OBJ-025), rotation de clé
  report v2.
- `docs/TUTORIAL.md` — guide d'intégration détaillé.
- `docs/JURIDIQUE.md` — cadrage juridique (pseudonymisation vs
  anonymisation RGPD, *EDPS c. CRU*).
- `docs/MENACE.md` — modèle de menace (gestion de clé + 4 menaces §8).
- `docs/ADR/` — décisions architecturales (au moins 0001, 0002, 0003).
- `CONTRIBUTING.md` — ce fichier.
- `CHANGELOG.md` — changements par version (commence par `## 0.1.0`).

Principe: la doc doit refléter le **vrai** projet. Lisez `PLAN.md`,
`DECISIONS.md` et `PRD.md` avant d'écrire ou de modifier la
documentation; n'inventez pas. Si une limite n'est pas claire, lisez l'ADR
ou la décision correspondante.

---

## 7. ADR (Architecture Decision Records)

Les décisions architecturales majeures sont figées dans `docs/ADR/`.

- `0001-fpe-ff3.md` — FPE FF3-1, registre SQLite, empreinte HMAC,
  logging méta, figage gazetteer, dates bucket de mois, rotation de clé
  hors v1, cohérence inter-type, collision inter-type PRENOM/PATRONYME.
- `0002-pas-de-service-heberge.md` — anonyfy ne sera jamais un service
  hébergé (décision d'architecture irréversible).
- `0003-permutation-feistel-petits-domaines.md` — permutation keyée
  Feistel pour les petits domaines non-FPE (D22), points fixes (D23),
  préservation de la casse (D24), collision inter-type (D26).

Pour ajouter une décision, créez `docs/ADR/00NN-slug.md` avec le format
(Statut, Contexte, Options, Décision, Motif, Conséquences). Un ADR est
append-only: si une décision est renversée, ajoutez un nouvel ADR qui le
supplante et référencez l'ancien.

---

## 8. Signaler un bug ou une limite

- **Bug**: ouvrez une issue avec un reproducteur minimal (test qui
  échoue). Ne commitez pas de données personnelles dans le reproducteur.
- **Limite documentée** (pas un bug): voir `README.md` § « Ce que anonyfy
  ne fait pas », `docs/MENACE.md`, et les ADR. Les limites v1 sont
  assumées (ré-identification par contexte, dictionnaire de code,
  rotation de clé reportée v2, etc.); elles ne seront pas « corrigées »
  en v1 car elles sont structurelles.

---

## 9. Licence

En contribuant, vous acceptez que votre contribution soit publiée sous
licence Apache-2.0 (voir `LICENSE`). Aucune contribution sous licence
incompatible ne sera acceptée.

---

*Voir `.olgenius/PLAN.md` pour le plan complet et `.olgenius/DECISIONS.md`
pour le registre des décisions figées.*