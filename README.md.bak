# anonyfy

> Pseudonymisation réversible et déterministe des données personnelles françaises,
> avant transmission à un modèle de langage.

**anonyfy** substitue les identifiants personnels d'un texte par des valeurs
plausibles et de même type, de façon réversible. Le clair ne quitte jamais
l'infrastructure du client : ni vers un service, ni vers un disque, ni vers un
journal. Conçu pour les équipes françaises qui branchent un LLM sur des données
métier et veulent une réponse défendable à la question « et le RGPD ? ».

---

## Pourquoi

Toute équipe française qui branche un LLM sur des données métier se heurte à la
même question dans la première semaine : *qu'est-ce qu'on a le droit d'envoyer
chez le fournisseur ?* Les réponses actuelles sont mauvaises.

- **Ne rien envoyer** : on renonce à l'usage.
- **Tout envoyer** : on transfère des données personnelles à un sous-traitant hors
  périmètre, souvent hors UE, sans base solide.
- **Caviarder** (`[REDACTED]`) : on détruit le raisonnement du modèle et on ne peut
  plus recoller la réponse aux données réelles.
- **Presidio** : l'outil de référence est anglo-centré. Rien n'est natif sur le NIR,
  le SIRET, l'IBAN français ou les formats d'adresse, et il n'offre pas de
  pseudonymisation réversible à coffre clé.

anonyfy comble le vide laissé : substituer par des valeurs de même type, de façon
déterministe et réversible, sans que le clair ne quitte le client.

---

## Ce que c'est

Une bibliothèque Python et une CLI. Pas un service hébergé, jamais.

```python
from anonyfy import Vault

v = Vault(key=..., scope="dossier-1234")
masked = v.mask(texte)              # -> MaskedText(.text, .entities)
clair  = v.unmask(reponse_du_modele)
v.report()                          # journal exploitable par un DPO
```

```
anonyfy scan dossier/*.txt          # mode observation : détecte, ne modifie rien
anonyfy mask fichier.txt --scope d1234
anonyfy unmask reponse.txt --scope d1234
```

---

## Couverture de détection (v1)

Les identifiants structurés sont traités par expression régulière **plus validation
arithmétique** : c'est ce qui écrase les faux positifs. Les patronymes et adresses
reposent sur des gazetteers (INSEE, COG) et des déclencheurs contextuels
(`M.`, `Mme`, `Maître`, `né(e) le`, `demeurant`).

| Type | Méthode | Validation | Substitut |
|---|---|---|---|
| NIR (n° sécu) | regex | clé mod 97 | FPE, clé recalculée |
| SIREN / SIRET | regex | Luhn | FPE, Luhn recalculé |
| IBAN FR | regex | mod 97 | FPE, clé recalculée |
| TVA intracomm. FR | regex | clé | FPE |
| Carte bancaire | regex | Luhn | FPE |
| Téléphone FR | regex | plan de numérotation | FPE, préfixe préservé |
| Email | regex | syntaxe | partie locale FPE, domaine gazetteer |
| Plaque SIV | regex | format | FPE |
| Prénom / nom | gazetteer INSEE + déclencheurs | — | gazetteer + registre de scope |
| Commune / code postal | gazetteer COG INSEE | cohérence CP/commune | gazetteer |
| Date de naissance | regex + déclencheur | calendaire | décalage déterministe borné |

---

## Le positionnement juridique — à lire avant de l'utiliser

La pseudonymisation n'est **pas** l'anonymisation. Écrire « conforme RGPD » ici
serait faux et discréditerait le projet auprès du public juridique visé.

Le cadrage défendable est plus intéressant. Dans *EDPS c. CRU* (CJUE, septembre
2025), la Cour a retenu une approche **relative** de la notion de donnée
personnelle : des données pseudonymisées transmises à un destinataire qui ne
dispose d'aucun moyen raisonnable de ré-identifier peuvent ne pas constituer des
données personnelles *pour ce destinataire*. Si la clé et le registre restent chez
le client, c'est exactement la configuration vis-à-vis du fournisseur de LLM.

C'est un raisonnement **contextuel et encore discuté** par le CEPD. anonyfy le
présente comme un argument à instruire au cas par cas avec son conseil, pas comme
un blanc-seing. Cette honnêteté est un différenciateur : personne d'autre ne
l'écrit.

---

## Ce que anonyfy ne fait pas

Ces limites sont volontaires et assumées. Les dissimuler discréditerait l'outil.

1. **Ce n'est pas de l'anonymisation** au sens du RGPD. Voir le positionnement
   ci-dessus.
2. **La ré-identification par le contexte.** « Le dirigeant de la société de
   menuiserie de Moulidars » reste identifiant même si le nom est substitué. Aucun
   outil ne résout ça, et prétendre le contraire serait malhonnête.
3. **Le dictionnaire de code.** Un mapping déterministe *est* un code book. Qui
   obtient beaucoup de couples clair/substitut peut inverser. Mitigations : clé
   secrète par déploiement, sel par scope, rotation de clé.
4. **La compromission de la clé.** La clé permet de tout inverser. Elle doit vivre
   dans le gestionnaire de secrets du client, jamais dans le dépôt, jamais dans le
   journal.
5. **Les faux positifs sur les noms-mots courants.** « Boulanger », « rue Pierre »,
   « Mme Rose » produiront des faux positifs. C'est le prix de l'auditabilité, et
   c'est la justification d'une couche modèle optionnelle plus tard. Le mode
   observation existe pour les découvrir avant la production.
6. **Pas de service hébergé, jamais.** Le coffre et la clé restent chez le client.
   C'est une décision d'architecture, pas une étape de feuille de route, et c'est
   l'argument le plus fort.

---

## Principes d'architecture

Quatre invariants. Si une décision de conception les contredit, c'est la décision
qui a tort.

1. **Le clair ne franchit jamais la frontière.** Ni vers un service, ni vers un
   disque, ni vers un journal.
2. **Déterminisme scopé.** Dans un scope, une valeur produit toujours le même
   substitut. C'est ce qui préserve le fil d'une conversation et le cache de préfixe
   du fournisseur.
3. **Injectivité dans le scope.** Deux valeurs distinctes ne partagent jamais un
   substitut. Sans cette garantie, `unmask` est ambigu et le modèle fusionne deux
   personnes.
4. **Rien n'est démasqué qui n'ait été masqué.** `unmask` ne transforme que des
   substituts réellement émis. Un identifiant inventé par le modèle reste tel quel.

Détail dans `architecture.md` : flux aller/retour, génération des substituts (FPE
pour les identifiants, gazetteer + registre de scope pour le texte libre),
résolution des collisions, traitement des appels d'outils.

---

## Statut

Proposition · v0.1 · Août 2026. Le code n'est pas encore publié. Le jalon M0
(squelette du paquet, CI, licence) est en cours.

Feuille de route :

| Jalon | Contenu |
|---|---|
| **M0** | Squelette du paquet, CI, licence, README qui vend |
| **M1** | Validateurs structurés + FPE + aller-retour |
| **M2** | Gazetteers, registre de scope, résolution de collisions |
| **M3** | CLI, mode observation, journal, rapport |
| **M4** | Documentation, corpus de test public, billet de lancement |

## Licence

Apache-2.0 sur l'ensemble du cœur. La version libre résout entièrement le problème
d'un utilisateur seul : détection, substituts, réversibilité, registre, CLI, mode
observation. Une version support/entreprise pourra venir plus tard ; une version
hébergée du coffre ne viendra jamais, l'architecture l'interdit.

---

*Voir `PRD.md` pour le cahier des charges complet et `architecture.md` pour la
conception détaillée.*