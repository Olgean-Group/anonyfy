# Corpus réel annoté — indisponibilité

Ce répertoire **ne contient aucun document réel annoté**. Le corpus réel
annoté (≥ 50 documents annotés par un humain, décision D12/OBJ-017) est
**indisponible** dans ce dépôt public et le restera par conception.

## Pourquoi l'indisponibilité

Un corpus réel annoté pour le rappel est composé de documents contenant des
données personnelles identifiables (noms, NIR, SIRET, IBAN, téléphones, emails,
adresses). Ces données sont régies par le RGPD et ne doivent **jamais** figurer
dans un dépôt public. Le risque de fuite de données personnelles réelles
l'emporte sur le bénéfice d'un corpus embarqué.

## Conséquence pour le critère « rappel ≥ 98 % »

Le critère de rappel (PRD §10) est mesuré **uniquement** contre le corpus réel
annoté (D12). En l'absence de ce corpus, le rappel **n'est pas affiché** dans le
rapport d'acceptation (`scripts/acceptance_report.py`). La ligne `rappel` affiche
à la place « à instruire via anonyfy scan ». Le test
`tests/acceptance/test_recall_structured.py` est `pytest.skip` avec un message
clair tant qu'aucun corpus réel annoté n'est présent.

Le corpus synthétique (`tests/acceptance/corpus_synthetic/`) n'est **pas**
utilisé pour le rappel: il teste les validateurs conçus pour lui, ce qui
donnerait un rappel mécaniquement ~100 % et une surpromesse (D12). Il sert
uniquement à la non-régression (déterminisme, round-trip, injectivité, fuite).

## Instruire un corpus réel sur site client

Pour mesurer le rappel 98 % en conditions réelles, un corpus annoté doit être
instruit **sur site client**, hors de ce dépôt, à l'aide du mode observation de
la CLI (PRD F7, phase 17):

```
anonyfy scan --observe --scope client-001 --registry /chemin/registre.db \
    /repertoire/documents/
```

Le mode observation (`--observe`) détecte et journalise les spans (audit méta
uniquement, jamais le clair ni les substituts, D10) **sans substituer**: le
texte original est laissé inchangé. Un opérateur humain annote ensuite les spans
détectés (vrais positifs, faux positifs, faux négatifs) au format attendé
(un `.txt` + un `.jsonl` d'annotations par document), puis calcule le rappel:

```
rappel = vrais_positifs / (vrais_positifs + faux_négatifs)
```

Le seuil cible est ≥ 0,98 sur les types structurés (NIR, SIREN, SIRET, IBAN,
TVA, CB, téléphone, plaque, date) et ≥ 0,95 sur les patronymes en contexte
déclenché.

## Format attendu du corpus réel (référence)

Chaque document est composé de deux fichiers:

- `doc_XXX.txt`: le texte original (clair, jamais dans ce dépôt).
- `doc_XXX.ann.jsonl`: une ligne JSON par annotation, au format:

  ```json
  {"start": 12, "end": 19, "type": "PATRONYME", "value": "Dupont"}
  ```

  `start`/`end` sont les offsets dans le `.txt`, `type` est un `EntityType`
  (NIR, SIRET, IBAN, TVA, CARTE_BANCAIRE, TELEPHONE, PLAQUE_SIV,
  REFERENCE_DOSSIER, EMAIL, DATE, PATRONYME, PRENOM, COMMUNE, VOIE), `value` est
  le texte clair de l'annotation.

Le test `tests/acceptance/test_recall_structured.py` détecte automatiquement la
présence de ≥ 50 fichiers `.txt` dans ce répertoire. Si la condition est
remplie, le test mesure le rappel contre les annotations `.ann.jsonl`
correspondantes. Sinon, il `pytest.skip`.