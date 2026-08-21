# anonyfy v0.1.0 — pseudonymisation réversible déterministe des données FR

> Première version publiable. Août 2026.

**anonyfy** est une bibliothèque Python et une CLI de pseudonymisation
**réversible et déterministe** des données personnelles françaises, avant
transmission à un modèle de langage. Le clair ne quitte jamais l'infrastructure
du client: ni vers un service, ni vers un disque, ni vers un journal. Pas de
service hébergé, jamais — c'est une décision d'architecture, pas une étape de
feuille de route.

## Ce qu'anonyfy fait

- Détecte les identifiants personnels français (NIR, SIREN, SIRET, IBAN, TVA,
  carte bancaire, téléphone FR, email, plaque SIV, prénom, nom, commune, voie,
  date de naissance, référence de dossier configurable) par regex **plus**
  validation arithmétique (Luhn, mod 97) pour écraser les faux positifs.
- Substitue chaque identifiant par une valeur **plausible de même type**,
  déterministe et réversible: FPE FF3-1 sur les grands domaines, permutation
  keyée Feistel sur les petits domaines non-FPE, gazetteer + registre de scope
  pour le texte libre.
- Garantit la **réversibilité** via un registre de scope SQLite (invariant 4:
  rien n'est démasqué qui n'ait été masqué; un identifiant inventé par le
  modèle reste tel quel).
- Garantit le **déterminisme scopé** (même valeur → même substitut dans un
  scope) et l'**injectivité** (deux valeurs distinctes ne partagent jamais un
  substitut).
- Retrouve les substituts dans la réponse du modèle **même reformatée**
  (groupes de chiffres, « M. Leroy » vs « Marc Leroy ») via un automate
  Aho-Corasick + dictionnaire de variantes normalisées.
- Journal d'audit HMAC-SHA-256 keyé, **méta uniquement** (jamais le texte, ni
  les substituts), rapport lisible par un DPO.
- CLI `anonyfy scan|mask|unmask`, mode observation (détecte, journalise, ne
  modifie rien), politique de fermeture `permissive`/`strict`.
- `mask_json` / `unmask_json` parcourent un payload JSON et ne masquent que les
  feuilles chaîne (jamais les clés, jamais `function.name`). C'est une
  **primitive, pas un proxy** compatible OpenAI — le proxy est prévu en v2.

```python
from anonyfy import Vault

v = Vault(key=..., scope="dossier-1234")
masked = v.mask(texte)              # -> MaskedText(.text, .entities)
clair  = v.unmask(reponse_du_modele)
v.report()                          # synthèse lisible par un DPO
```

## Installation

```bash
uv add anonyfy
```

Python ≥ 3.11. Le cœur ne dépend que de la bibliothèque standard et d'une
bibliothèque cryptographique (FPE FF3-1 via `ff3`, isolée derrière
`surrogate/fpe.py`). Aucun téléchargement de modèle, fonctionne hors ligne.

Voir le [README](../../README.md) pour le tutoriel 30 secondes, et
[`docs/TUTORIAL.md`](../TUTORIAL.md) pour le guide d'intégration détaillé.

## Positionnement juridique — à lire avant de l'utiliser

La pseudonymisation n'est **pas** l'anonymisation au sens du RGPD. anonyfy ne
le prétend jamais.

Le cadrage défendable est contextuel: dans *EDPS c. CRU* (CJUE, septembre 2025),
la Cour a retenu une approche **relative** de la notion de donnée
personnelle — des données pseudonymisées transmises à un destinataire qui ne
dispose d'aucun moyen raisonnable de ré-identifier peuvent ne pas constituer
des données personnelles *pour ce destinataire*. Si la clé et le registre
restent chez le client, c'est exactement la configuration vis-à-vis du
fournisseur de LLM.

C'est un argument à instruire au cas par cas avec son conseil, pas un
blanc-seing. Voir [`docs/JURIDIQUE.md`](../JURIDIQUE.md).

## Limites v1 — volontaires et assumées

Les dissimuler discréditerait l'outil. Aucune surpromesse dans ce billet.

1. **Ce n'est pas de l'anonymisation** au sens du RGPD. Voir ci-dessus.
2. **Ré-identification par le contexte.** « Le dirigeant de la société de
   menuiserie de Moulidars » reste identifiant même si le nom est substitué.
   Aucun outil ne résout ça.
3. **Dictionnaire de code.** Un mapping déterministe *est* un code book. Qui
   obtient beaucoup de couples clair/substitut peut inverser. Mitigations:
   clé secrète par déploiement, sel par scope.
4. **Compromission de la clé.** La clé permet de tout inverser. Elle doit vivre
   dans le gestionnaire de secrets du client, jamais dans le dépôt, jamais
   dans le journal. Voir [`docs/MENACE.md`](../MENACE.md).
5. **FPE sur petits domaines.** FF3-1 est faible quand l'espace des valeurs
   est réduit. anonyfy tranche par type: FPE pur sur les grands domaines;
   permutation keyée Feistel (ADR 0003) sur les petits domaines. La
   bijectivité est garantie, mais les points fixes existent (probabilité
   ~1/N par clair, détectés et alertés). Voir ADR 0001 et ADR 0003.
6. **Dates par bucket de mois.** Le décalage (D8) préserve le mois et l'année
   mais pas le jour (clampé à [1, 28]). Une date substituée reste
   ré-identifiable par contexte si le bucket est unique.
7. **Rotation de clé hors périmètre v1.** Reportée à v2 (exigerait un registre
   stockant du clair, interdit par l'invariant 1 en v1).
8. **Cohérence inter-type non garantie.** SIREN/SIRET/TVA intracommunautaire
   partagent le même SIREN sous-jacent; anonyfy applique FPE indépendamment par
   type (OBJ-008). Reporté à v2.
9. **Collision inter-type PRENOM/PATRONYME (D26).** `RegistryError` rare en
   production; workaround re-key, solution v2 sondage registre + offset.
10. **Faux positifs sur noms-mots courants.** « Boulanger », « rue Pierre »,
    « Mme Rose » produisent des faux positifs. Le mode observation existe pour
    les découvrir avant la production.
11. **`mask_json` est une primitive, pas un proxy.** Le proxy compatible
    OpenAI est prévu en v2 (OBJ-025).

## Rappel 98 % — à instruire via `anonyfy scan`

Le critère de rappel ≥ 98 % (PRD §10) est mesuré **uniquement** contre un
corpus réel annoté par un humain (décision D12). Aucun corpus réel annoté
n'est embarqué dans ce dépôt public — et le restera par conception: un corpus
réel annoté est composé de données personnelles identifiables régies par le
RGPD, qui ne doivent jamais figurer dans un dépôt public.

En l'absence de corpus réel annoté, **anonyfy n'affiche pas 98 % de rappel**.
La ligne `rappel` du rapport d'acceptation affiche à la place
« à instruire via `anonyfy scan` ». Le corpus synthétique livré sert
uniquement à la non-régression (déterminisme, round-trip, injectivité, fuite),
pas au rappel: tester les validateurs conçus pour lui donnerait un rappel
mécaniquement ~100 % et une surpromesse.

Pour instruire le rappel en conditions réelles, un corpus annoté doit être
constitué **sur site client**, hors de ce dépôt, à l'aide du mode observation:

```
anonyfy scan --observe --scope client-001 --registry /chemin/registre.db \
    /repertoire/documents/
```

## Architecture — quatre invariants

1. **Le clair ne franchit jamais la frontière.** Ni vers un service, ni vers un
   disque, ni vers un journal.
2. **Déterminisme scopé.** Dans un scope, une valeur produit toujours le même
   substitut.
3. **Injectivité dans le scope.** Deux valeurs distinctes ne partagent jamais
   un substitut.
4. **Rien n'est démasqué qui n'ait été masqué.**

Voir `architecture.md` et les ADR (`docs/ADR/`) pour les décisions
cryptographiques figées.

## Feuille de route

| Jalon | Contenu | Statut |
|---|---|---|
| M0 | Squelette, CI, licence, README | Livré |
| M1 | Validateurs structurés + FPE + aller-retour | Livré |
| M2 | Gazetteers, registre de scope, résolution de collisions | Livré |
| M3 | CLI, mode observation, journal, rapport | Livré |
| M4 | Documentation, corpus de test, billet de lancement | Livré |

v2 (non datée): rotation de clé, cohérence inter-type, proxy compatible OpenAI,
solution sondage registre + offset pour la collision inter-type.

## Licence

Apache-2.0 sur l'ensemble du cœur. La version libre résout entièrement le
problème d'un utilisateur seul. Une version support/entreprise pourra venir
plus tard; une version hébergée du coffre ne viendra jamais — l'architecture
l'interdit.

---

*Sources: [README](../../README.md), [CHANGELOG](../../CHANGELOG.md),
[PRD](../../PRD.md), [architecture.md](../../architecture.md),
[docs/JURIDIQUE.md](../JURIDIQUE.md), [docs/MENACE.md](../MENACE.md),
[docs/TUTORIAL.md](../TUTORIAL.md), [docs/ADR/](../ADR/).*