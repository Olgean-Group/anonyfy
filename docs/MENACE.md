# Modèle de menace — gestion de la clé anonyfy

> Décision D11 (CLI: sécurité de la clé et registre persistant).
> La clé FPE est la racine du montage (architecture §8 point 3): sa fuite
> compromet l'ensemble des substituts émis dans le scope. Ce document recense
> les menaces sur la gestion de clé et les contre-mesures applicables.

## Menace 1 — Clé passée en argument CLI (visible via `ps`)

**Menace**: une clé passée en clair sur la ligne de commande
(`anonyfy mask ... --key 00...`) est visible par tout processus du système
via `ps`, `/proc`, ou l'historique shell. La clé est ainsi compromise dès
l'invocation.

**Contre-mesure**: la CLI anonyfy refuse `--key` en clair. La clé ne peut
provient que de:
- la variable d'environnement `ANONYFY_KEY` (hex), ou
- un fichier `--key-file <path>` contenant la clé hex (mode `0600`).

Tout passage de `--key` provoque une erreur et l'arrêt de la commande.

## Menace 2 — Fichier de clé lisible par groupe ou autre

**Menace**: un fichier de clé en mode `0644` (lisible par groupe/autre) expose
la clé à tout utilisateur du système pouvant lire le fichier.

**Contre-mesure**: `--key-file` refuse un fichier dont le mode autorise le
groupe ou autre (`st_mode & 0o077 != 0`). Le mode attendu est `0600`
(lecture/écriture propriétaire) ou `0400` (lecture propriétaire seule). Un
fichier en `0644` est refusé avec un message d'erreur explicite.

## Menace 3 — Clé héritée de l'environnement par les sous-processus

**Menace**: une clé définie via `ANONYFY_KEY` est héritée par défaut par tous
les sous-processus lancés depuis la session. Un sous-processus tiers (outil,
script, modèle) peut alors lire la clé dans son environnement.

**Contre-mesure**: la CLI affiche un avertissement (warning) sur stderr lorsque
la clé provient de `ANONYFY_KEY`, rappelant qu'elle peut fuiter vers les
sous-processus. En production, préférez `--key-file` (non hérité) ou purgez
l'environnement avant de lancer des sous-processus (`env -u ANONYFY_KEY`).

## Menace 4 — Clé stockée en clair dans le code source ou un config

**Menace**: une clé écrite en dur dans le code, un notebook, ou un fichier de
config versionné est compromise de façon permanente.

**Contre-mesure**: ne jamais écrire la clé dans le code. Utiliser un
**gestionnaire de secrets** (HashiCorp Vault, AWS Secrets Manager, Doppler,
Infisical) ou un service de chargement de clé par le système
(`systemd-load-key`, `systemd-creds`, fichiers de clé provisionnés par le
secret manager avec mode `0600`). La clé est injectée au runtime, jamais
commitée.

## Menace 5 — Registre persistant non chiffré (D4)

**Menace**: le registre SQLite (D4) est non chiffré (par choix: il ne stocke
jamais de clair, uniquement indices/substituts/HMAC). Un accès au fichier de
registre permet de lier des substituts entre eux (code book partiel).

**Contre-mesure**: le registre ne contient jamais de valeur claire (invariant
1, D4). L'accès au fichier de registre doit être restreint par les permissions
du système de fichiers (mode `0600` recommandé, propriétaire du processus
anonyfy). Le registre n'est pas sensible au sens RGPD (pas de clair), mais sa
divulgation facilite la corrélation: protéger le fichier par les permissions
OS.

## Menace 6 — Compromission de la clé (rotation)

**Menace**: si la clé est compromise, tous les substituts émis dans le scope
sont déchiffrables par l'attaquant.

**Contre-mesure**: la rotation de clé est **hors périmètre v1** (OBJ-009/024,
T1): après rotation K→K', les substituts FPE et les HMAC du registre ne sont
plus déchiffrables/vérifiables sans stocker le clair (interdit par invariant 1).
La rotation est reportée à v2 (registre enveloppe-chiffrée sous KMS). En
attente, la mitigation est préventive: protéger la clé (gestionnaire de
secrets, `systemd-load-key`), restreindre l'accès au fichier de clé, et
démarrer un nouveau scope+registre si compromission suspectée (les anciens
substituts ne sont plus déchiffrables, mais l'attaque est contenue au scope
compromis).

## Modèle de menace du projet (PRD §8)

Au-delà de la gestion de clé (menaces 1 à 6 ci-dessus), le PRD §8
recense quatre menaces structurelles que la pseudonymisation réversible
**ne résout pas**. Les documenter explicitement est un différenciateur:
personne d'autre ne le fait, et les dissimuler discréditerait l'outil.

### Menace 7 — Ré-identification par le contexte

La **ré-identification par le contexte** est le risque résiduel de toute
pseudonymisation. Un substitut peut ré-identifier si le contexte autour est
unique. « Le
dirigeant de la société de menuiserie de Moulidars » reste identifiant
même si le nom est substitué. Aucun outil ne résout ça, et prétendre le
contraire serait malhonnête. Le risque est résiduel et accepté (PRD §8
point 1, *EDPS c. CRU* — raisonnement contextuel, voir `docs/JURIDIQUE.md`).

### Menace 8 — Dictionnaire de code

Le **dictionnaire de code** est la faiblesse inhérente au mapping déterministe.
Un mapping déterministe *est* un code book. Qui obtient un grand nombre de
couples clair/substitut pour un scope peut inverser. Mitigations: clé
secrète par déploiement, sel par scope (déterminisme scopé, invariant 2).
La rotation de clé est reportée à v2 (T1, ADR 0001 §13): elle exigerait
un registre stockant du clair, interdit par l'invariant 1.

### Menace 9 — Compromission de la clé

La **compromission de la clé** est la menace racine: la clé permet de tout
inverser. C'est la racine du montage (menaces 1 à 6
ci-dessus). La clé doit vivre dans le gestionnaire de secrets du client,
jamais dans le dépôt, jamais dans le journal, jamais en argument CLI en
clair. Toute la pseudonymisation tombe si la clé est compromise.

### Menace 10 — FPE sur petits domaines

FF3-1 est faible quand l'espace des valeurs possibles est réduit (plaque
SIV ~1000 valeurs, référence de dossier configurable). anonyfy tranche par
type (D2, ADR 0001 §4): FPE pur sur les grands domaines (NIR, SIREN,
SIRET, IBAN, TVA, carte bancaire, téléphone); permutation keyée Feistel
(ADR 0003) sur les petits domaines non-FPE (patronyme, prénom, commune,
voie, plaque SIV, référence de dossier, date, email local-part). La
bijectivité est garantie, mais les points fixes existent (D23:
probabilité ~1/N par clair, détectés et alertés, jamais silencieux).

### Menace 11 — Date par bucket de mois (D8)

La date substituée est ré-identifiable par contexte: le décalage par
bucket de mois (D8, ADR 0001 §10) préserve le mois et l'année mais pas
le jour (clampé à [1, 28]). Un bucket de date ou un mois NIR reste
ré-identifiable si le contexte autour est unique. La limite est assumée
et documentée (PRD §8 point 1): le décalage ne prétend pas empêcher la
ré-identification par contexte.

---

## Recommandations de déploiement

1. **Provisionner la clé** via un gestionnaire de secrets ou `systemd-creds`,
   écrit dans un fichier temporaire en mode `0600`, référencé par
   `--key-file`.
2. **Purger `ANONYFY_KEY`** avant de lancer des sous-processus non de confiance
   (`env -u ANONYFY_KEY`), ou préférer `--key-file`.
3. **Restreindre le fichier de registre** (`chmod 0600 reg.db`), propriétaire du
   processus anonyfy.
4. **Ne jamais logger la clé** (la CLI ne l'affiche jamais; invariant 1).
5. **Journaliser les accès** via `--audit` (méta uniquement: scope, compte par
   type, règle, empreinte HMAC-SHA-256(key, texte) — jamais le texte, D3/D10).