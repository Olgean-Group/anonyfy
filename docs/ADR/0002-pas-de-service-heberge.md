# ADR 0002 — anonyfy ne sera jamais un service hébergé

Statut: Accepté · Date: Août 2026 · Phase: 03 (M0)

Décision d'architecture, pas une étape de feuille de route. Le PRD (§4 non-objectifs,
§11 modèle économique) et le README l'affirment; cet ADR le formalise comme
décision irréversible. Références: `PRD.md` §4 (non-objectifs), §11 (licence et
modèle économique), `.olgenius/PLAN.md` phase 03.

---

## 1. Contexte

La valeur du projet pour un client français tient à un argument unique: le clair
ne quitte jamais son infrastructure (PRD §8, invariant 1). Un service hébergé
introduirait, par construction, un chemin où le clair transite vers un
sous-traitant (l'hébergeur du service), ce qui:

- contredit l'invariant 1 (« le clair ne franchit jamais la frontière ») et la
  promesse « jamais de clair stocké »;
- affaiblit le positionnement juridique (PRD §9, *EDPS c. CRU*): la configuration
  défendable repose sur le fait que le destinataire (le fournisseur de LLM) ne
  dispose d'aucun moyen raisonnable de ré-identifier **parce que la clé et le
  registre restent chez le client**; un service hébergé devient lui-même un
  tiers qui manipule du clair;
- crée une surface d'attaque (un coffre centralisé concentre les clés de tous
  les clients) et un risque commercial (dépendance à l'hébergeur pour un outil
  qui se veut auditabile bout en bout).

## 2. Décision

**anonyfy ne sera jamais un service hébergé.** Le code est livré comme une
**bibliothèque Python** (installable via `uv add anonyfy`) et une CLI; le client
l'exécute dans son propre périmètre, sur son infrastructure, avec sa propre clé
et son propre registre de scope.

Aucune forme d'hébergement du coffre, du registre ou de la clé n'est prévue, en
v1 comme en v2 ou au-delà. Un proxy v2 compatible OpenAI (PRD §4), s'il vient,
est exécuté côté client, jamais comme un service managé par le projet.

## 3. Motif

- **Sécurité**: la clé est la racine du montage (PRD §8 point 3). La concentrer
  dans un service centralisé crée une cible unique; la garder chez le client
  supprime cette cible.
- **Confiance**: un client qui peut lire le code, l'auditer et l'exécuter
  lui-même n'a pas à faire confiance à un tiers. C'est le public visé (PRD §3:
  équipes qui mettent les mains dans le cambouis).
- **Juridique**: le positionnement *EDPS c. CRU* (PRD §9, `docs/JURIDIQUE.md`)
  repose sur la clé et le registre chez le client. Un service hébergé détruit
  cet argument.
- **Économique**: la version libre résout entièrement le problème d'un
  utilisateur seul (PRD §11). Le modèle de revenu vient du support et de
  l'accompagnement, pas d'un service managé. La décision d'architecture rend
  l'offre hébergée impossible, et c'est l'argument le plus fort.

## 4. Conséquences

- **Le clair ne quitte jamais l'infrastructure du client**: ni vers un service,
  ni vers un disque externe, ni vers un journal. L'invariant 1 est structurel,
  pas optionnel.
- **Pas de télémétrie**: aucune donnée d'usage, aucune métrique, aucun appel
  réseau du cœur vers l'extérieur. anonyfy fonctionne intégralement hors ligne
  (PRD §6). Un intégrateur qui ajouterait sa propre télémétrie le fait sous sa
  propre responsabilité, hors du périmètre du projet.
- **Aucune dépendance à un service externe**: la détection, les substituts, la
  réversibilité, le registre et la CLI sont livrés dans le paquet. Les
  gazetteers sont embarqués (< 20 Mo), pas téléchargés au runtime.
- **Le projet ne se vendra jamais comme un service hébergé du coffre**. Le
  support, les connecteurs propriétaires, la gestion centralisée des règles et
  l'accompagnement restent possibles (PRD §11); l'hébergement du coffre non.
- **Maintenance**: un mainteneur nommé peut arrêter le projet, mais ne peut pas
  en faire un service hébergé sans révoquer cette décision d'architecture
  (ce qui le décrédibiliserait auprès du public juridique visé).