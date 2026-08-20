# anonyfy — PRD

> Bibliothèque Python de pseudonymisation réversible et déterministe des données
> personnelles françaises, avant transmission à un modèle de langage.
>
> Statut : proposition · Version 0.1 · Août 2026 · Olgean

---

## 1. Problème

Toute équipe française qui branche un LLM sur des données métier se heurte à la même
question dans la première semaine : *qu'est-ce qu'on a le droit d'envoyer chez le
fournisseur ?* Les réponses actuelles sont mauvaises.

- **Ne rien envoyer** : on renonce à l'usage.
- **Tout envoyer** : on transfère des données personnelles à un sous-traitant hors
  périmètre, souvent hors UE, sans base solide.
- **Caviarder** (`[REDACTED]`) : on détruit le raisonnement du modèle et on ne peut
  plus recoller la réponse aux données réelles.
- **Presidio** : l'outil de référence est anglo-centré. La reconnaissance d'entités
  est entraînée sur l'anglais, rien n'est natif sur le NIR, le SIRET, l'IBAN français
  ou les formats d'adresse, et il n'offre pas de pseudonymisation réversible à coffre
  clé — or c'est précisément ce dont on a besoin quand la réponse du modèle doit être
  réinjectée dans un système du client.

Il manque une brique : **substituer les données personnelles par des valeurs
plausibles et de même type, de façon déterministe et réversible, sans que le clair
ne quitte jamais l'infrastructure du client.**

---

## 2. Objectifs

| # | Objectif | Mesure |
|---|---|---|
| O1 | Détecter les identifiants personnels français dans du texte libre | Rappel ≥ 98 % sur les types structurés |
| O2 | Substituer sans dégrader le raisonnement du modèle | Substituts valides et de même type que l'original |
| O3 | Réversibilité exacte | `unmask(mask(x)) == x` sur 100 % du corpus de test |
| O4 | Déterminisme scopé | Sortie identique bit à bit sur exécutions répétées |
| O5 | Préserver le cache du fournisseur | Préfixe de prompt stable entre appels d'un même scope |
| O6 | Auditabilité | Chaque substitution traçable jusqu'à la règle qui l'a décidée |

### Non-objectifs (v1)

- **Ce n'est pas de l'anonymisation** au sens du RGPD, et la documentation doit le dire
  en toutes lettres. Voir §9.
- **Pas de détection par modèle.** La v1 est entièrement déterministe : validateurs,
  gazetteers, déclencheurs contextuels. Une couche NER viendra plus tard, en option.
- **Pas de proxy.** La v2 exposera un proxy compatible OpenAI ; la v1 est une
  bibliothèque et une CLI.
- **Pas de traitement d'images ou de PDF.** L'extraction se fait en amont.
- **Pas de service hébergé, jamais.** Le coffre et la clé restent chez le client. C'est
  une décision d'architecture, pas une étape de feuille de route.
- **Pas de couverture multi-pays en v1.** Le français est le périmètre et
  la raison d'être du projet.

---

## 3. Utilisateurs cibles

| Profil | Besoin | Ce qu'il fait avec |
|---|---|---|
| Développeur qui intègre un LLM | Ne pas être le responsable de la fuite | 3 lignes autour de son appel API |
| Data engineer sur données clients | Traiter en masse sans exposer le corpus | Pipeline batch, mode observation d'abord |
| PME sans DPO dédié | Une réponse défendable à « et le RGPD ? » | La CLI en mode `scan`, puis le rapport |
| Cabinet / service juridique | Documenter ce qui a été transmis | Le journal d'audit et le rapport DPO |

Le public visé met les mains dans le cambouis : il installe, il lit le code, il ouvre
des issues. La v1 doit être utilisable en trente secondes après `uv add anonyfy`.

---

## 4. Périmètre

### v1 — la bibliothèque (ce document)

```python
from anonyfy import Vault

v = Vault(key=..., scope="dossier-1234")
masked = v.mask(texte)                 # -> MaskedText(.text, .entities)
clair  = v.unmask(reponse_du_modele)
v.report()                             # journal exploitable par un DPO
```

Plus une CLI :

```
anonyfy scan dossier/*.txt          # mode observation : détecte, ne modifie rien
anonyfy mask fichier.txt --scope d1234
anonyfy unmask reponse.txt --scope d1234
```

### v2 — le proxy (hors périmètre, mais l'API doit lui laisser la place)

Proxy compatible OpenAI, masquage des `messages[]` et `tools[]`, démasquage des
`tool_calls.arguments`, masquage des `tool_results`, gestion du streaming.
`mask_json()` est prévu dans l'API publique dès la v1 même s'il reste minimal.

---

## 5. Exigences fonctionnelles

**F1 — Détection.** Le moteur détecte les types listés en §7 et retourne des spans
`(début, fin, type, valeur, règle, confiance)`.

**F2 — Arbitrage des chevauchements.** Quand deux détecteurs se recouvrent, la règle
la plus spécifique gagne (un SIRET valide bat « suite de 14 chiffres »), puis la plus
longue, puis la priorité déclarée. La décision est journalisée.

**F3 — Substituts de même type.** Un nom devient un nom français plausible, un SIRET
devient un SIRET valide au format, une date devient une date. Jamais de jeton opaque
du type `PERSONNE_1` : cela détruit la fluidité grammaticale et le raisonnement.

**F4 — Déterminisme scopé.** Dans un même `scope`, une valeur donne toujours le même
substitut. Entre deux scopes distincts, les substituts diffèrent.

**F5 — Absence de collision.** Deux valeurs claires distinctes ne partagent jamais un
substitut à l'intérieur d'un scope. *(Contrainte non triviale : voir ARCHITECTURE.md §5.)*

**F6 — Réversibilité contrôlée.** `unmask()` ne remplace que des substituts
effectivement émis dans le scope. Un identifiant inventé par le modèle n'est jamais
transformé en une fausse valeur claire.

**F7 — Mode observation.** Un mode qui détecte, journalise et ne modifie rien. C'est
la condition d'adoption : personne ne met ça dans le chemin critique sans avoir vu
d'abord ce qui aurait été remplacé.

**F8 — Politique de fermeture.** Configurable : `permissive` (on laisse passer ce
qu'on n'a pas su qualifier) ou `strict` (on lève une exception si un span de confiance
faible n'est pas résolu). Défaut `permissive` en v1, avec avertissement.

**F9 — Journal d'audit.** Pour chaque appel : horodatage, scope, nombre de spans par
type, règle déclenchée, empreinte du texte. **Jamais la valeur claire.**

**F10 — Rapport.** `report()` produit une synthèse lisible par un non-développeur :
types rencontrés, volumes, règles actives, versions des gazetteers.

---

## 6. Exigences non fonctionnelles

| Exigence | Cible |
|---|---|
| Latence | `mask()` < 50 ms pour 10 000 caractères, mono-thread, sans réseau |
| Empreinte | Aucun téléchargement de modèle ; gazetteers embarqués < 20 Mo |
| Dépendances | Le cœur ne dépend que de la bibliothèque standard + une lib crypto |
| Python | ≥ 3.11 |
| Déterminisme | 1 000 exécutions du même corpus, même scope → sortie identique bit à bit |
| Thread-safety | Un `Vault` est utilisable depuis plusieurs threads |
| Portabilité | Aucune dépendance à un service externe, fonctionne hors ligne |

---

## 7. Couverture de détection v1

Les identifiants structurés sont traités par expression régulière **plus validation
arithmétique** — c'est ce qui écrase les faux positifs. Les patronymes et adresses ne
sont pas régulables : ils reposent sur des gazetteers et des déclencheurs contextuels.

| Type | Méthode | Validation | Substitut |
|---|---|---|---|
| NIR (n° de sécurité sociale) | regex | clé de contrôle mod 97 | FPE, clé recalculée |
| SIREN / SIRET | regex | Luhn | FPE, Luhn recalculé |
| IBAN FR | regex | mod 97 | FPE, clé recalculée |
| TVA intracommunautaire FR | regex | clé | FPE |
| Carte bancaire | regex | Luhn | FPE |
| Téléphone FR | regex | plan de numérotation | FPE, préfixe préservé |
| Email | regex | syntaxe | partie locale par FPE, domaine par gazetteer |
| Plaque SIV | regex | format | FPE |
| Référence de dossier | regex configurable par le client | — | FPE |
| Prénom / nom | gazetteer INSEE + déclencheurs (`M.`, `Mme`, `Maître`, `né(e) le`, `demeurant`) | — | gazetteer + registre de scope |
| Commune / code postal | gazetteer COG INSEE | cohérence CP/commune | gazetteer, département préservé en option |
| Voie / adresse | déclencheurs + base adresse | partielle | gazetteer |
| Date de naissance | regex + déclencheur | calendaire | décalage déterministe borné, intervalles préservés |

**Le plafond, à documenter dans le README.** Les règles ne lèvent pas l'ambiguïté :
« Boulanger », « rue Pierre », « Mme Rose » produiront des faux positifs. C'est le
prix de l'auditabilité, et c'est la justification d'une couche modèle optionnelle
plus tard — pas un défaut à dissimuler.

---

## 8. Modèle de menace

**Ce que le projet protège.** La transmission de données personnelles à un
fournisseur de LLM, qui est un sous-traitant hors du périmètre de traitement initial.

**Ce qu'il ne protège pas.**

1. **La ré-identification par le contexte.** « Le dirigeant de la société de menuiserie
   de Moulidars » reste identifiant même si le nom est substitué. Aucun outil ne résout
   ça, et prétendre le contraire serait malhonnête.
2. **Le dictionnaire de code.** Un mapping déterministe *est* un code book. Qui obtient
   un grand nombre de couples clair/substitut peut inverser. Mitigations : clé secrète
   par déploiement, sel par scope, rotation de clé prévue dès la v1.
3. **La compromission de la clé.** La clé permet de tout inverser. Elle doit vivre dans
   le gestionnaire de secrets du client, jamais dans le dépôt, jamais dans le journal.
4. **Le FPE sur petits domaines.** FF3-1 est faible quand l'espace des valeurs possibles
   est réduit. À documenter type par type, avec repli sur le registre là où le domaine
   est trop petit.

**Ce que le projet ne stocke jamais.** Aucune valeur claire n'est écrite sur disque —
ni dans le registre de scope, ni dans le journal d'audit. C'est ce qui permet de dire
au client qu'il n'introduit pas une nouvelle base sensible dans son infrastructure.

---

## 9. Cadre juridique — le positionnement

La pseudonymisation n'est **pas** l'anonymisation. Écrire « conforme RGPD » sur le
dépôt serait faux et nous discréditerait auprès du public juridique que nous visons.

Le cadrage défendable est plus intéressant. Dans *EDPS c. CRU* (CJUE, septembre 2025),
la Cour a retenu une approche **relative** de la notion de donnée personnelle : des
données pseudonymisées transmises à un destinataire qui ne dispose d'aucun moyen
raisonnable de ré-identifier peuvent ne pas constituer des données personnelles *pour
ce destinataire*. Si la clé et le registre restent chez le client, c'est exactement la
configuration vis-à-vis du fournisseur de LLM.

C'est un raisonnement **contextuel et encore discuté** par le CEPD. La documentation
doit le présenter comme un argument à instruire au cas par cas avec son conseil, pas
comme un blanc-seing. Cette honnêteté est un différenciateur : personne d'autre ne
l'écrit.

---

## 10. Critères d'acceptation v1

- [ ] Rappel ≥ 98 % sur les types structurés (corpus de test synthétique + corpus annoté réel)
- [ ] Précision ≥ 95 % sur les patronymes en contexte déclenché
- [ ] `unmask(mask(x)) == x` sur 100 % du corpus
- [ ] Aucune fuite : recherche de chaque valeur claire dans la sortie → zéro occurrence
- [ ] Zéro collision sur un corpus contenant 5 000 patronymes distincts dans un scope
- [ ] Déterminisme : 1 000 exécutions → sortie identique bit à bit
- [ ] `mask()` < 50 ms pour 10 000 caractères
- [ ] Installation à froid et premier masquage réussi en moins de 30 secondes
- [ ] README qui énonce explicitement les limites du §8

Le test « zéro collision sur 5 000 patronymes » n'est pas décoratif : c'est le
scénario du contentieux de masse, et c'est là que les implémentations naïves cassent.

---

## 11. Licence et modèle économique

**Licence : Apache-2.0** sur l'ensemble du cœur. L'AGPL protégerait d'un risque
théorique à notre échelle et ferait fuir les DSI françaises, qui sont exactement le
public que nous voulons atteindre.

**Ce qui reste gratuit, pour toujours** : la détection, les substituts, la
réversibilité, le registre, la CLI, le mode observation. La version libre doit
résoudre *entièrement* le problème d'un utilisateur seul.

**Ce qui peut se vendre plus tard** : support et engagement de service, connecteurs
propriétaires, mode politique avancé et gestion centralisée des règles, rapports
d'audit destinés à un régulateur, accompagnement à l'intégration.

**Ce qui ne se vendra jamais** : une version hébergée du coffre. L'architecture
l'interdit, et c'est notre argument le plus fort.

Horizon réaliste : 12 à 18 mois entre la première étoile et le premier euro. Ce
projet est un canal de notoriété avant d'être une ligne de revenu.

---

## 12. Risques

| Risque | Probabilité | Impact | Réponse |
|---|---|---|---|
| Microsoft étend Presidio au français | Moyenne | Élevé | Tenir la position sur la réversibilité, le registre et l'audit — ce qu'ils ne feront pas |
| Faux positifs sur les noms-mots courants | Élevée | Moyen | Mode observation par défaut, déclencheurs contextuels, liste d'exclusion configurable |
| Collisions de substituts en corpus dense | Certaine sans mitigation | Élevé | Registre de scope avec sondage déterministe (ARCHITECTURE.md §5) |
| FPE faible sur petits domaines | Certaine | Moyen | Repli sur registre, documenté type par type |
| Personne ne maintient après trois mois | Réelle | Élevé | Un mainteneur nommé, une règle d'arrêt fixée à froid |
| Le nom est déjà déposé | Faible | Faible | `anonyfy` est libre sur PyPI ; vérification INPI à faire |

---

## 13. Jalons

| Jalon | Contenu | Sortie |
|---|---|---|
| **M0** | Squelette du paquet, CI, licence, README qui vend | Dépôt public vide mais lisible |
| **M1** | Validateurs structurés + FPE + aller-retour | `mask`/`unmask` sur identifiants |
| **M2** | Gazetteers, registre de scope, résolution de collisions | Patronymes et adresses |
| **M3** | CLI, mode observation, journal, rapport | Utilisable en production |
| **M4** | Documentation, corpus de test public, billet de lancement | Publication |

Le M4 n'est pas un jalon de finition : c'est le seul qui détermine si le projet existe.

---

*Voir `ARCHITECTURE.md` pour le flux détaillé, la génération des substituts et le
traitement des appels d'outils.*
