# Cadre juridique — positionnement honnête

> Squelette cadrant créé en phase 03. La phase 20 le complétera. Statut: v0.1 · Août 2026.

Ce document présente le positionnement juridique d'anonyfy **tel qu'il doit être
instruit au cas par cas avec le conseil du client**. anonyfy n'est pas un conseil
juridique. L'objectif est l'honnêteté: ne pas surpromettre « conforme RGPD » là où
la réalité est plus nuancée et plus intéressante.

---

## 1. Pseudonymisation n'est pas anonymisation

La pseudonymisation **n'est pas** l'anonymisation au sens du RGPD. Écrire
« conforme RGPD » sur le dépôt serait faux et discréditerait le projet auprès du
public juridique visé.

- **Anonymisation au sens RGPD**: les données sont rendues irréversiblement
  impossibles à ré-identifier, y compris par croisement avec d'autres sources.
  Le critère est élevé: un risque résiduel de ré-identification subsistant suffit
  à ce que les données restent personnelles. anonyfy **ne garantit pas** ce
  critère, et ne le prétend pas.
- **Pseudonymisation**: les données sont remplacées par des identifiants
  réversibles sous une clé tenue séparément. Les données pseudonymisées restent
  des données personnelles au sens du RGPD (la ré-identification est possible
  pour qui détient la clé). C'est précisément ce qu'anonyfy fait.

anonyfy est donc un outil de **pseudonymisation réversible**, pas un outil
d'anonymisation. La distinction est explicite dans le README (§ « Ce que anonyfy
ne fait pas ») et dans le PRD §9.

## 2. Le raisonnement défendable: *EDPS c. CRU*

Le cadrage intéressant est relatif, pas absolu. Dans l'affaire *EDPS c. CRU*
(CJUE, septembre 2025), la Cour a retenu une approche **relative** de la notion
de donnée personnelle: des données pseudonymisées transmises à un destinataire
qui ne dispose d'**aucun moyen raisonnable de ré-identifier** peuvent ne pas
constituer des données personnelles **pour ce destinataire**.

Si la clé et le registre de scope restent chez le client, c'est exactement la
configuration vis-à-vis du fournisseur de LLM: ce dernier reçoit des
substituts valides au format mais n'a aucun moyen raisonnable de remonter au
clair sans la clé. Le raisonnement défend l'idée que, **vis-à-vis du
fournisseur de LLM**, les données transmises peuvent ne pas constituer des
données personnelles.

## 3. Un raisonnement contextuel, pas un blanc-seing

C'est un raisonnement **contextuel et encore discuté** par le CEPD (Comité
européen de la protection des données). anonyfy le présente comme:

- un **argument à instruire au cas par cas** avec le conseil du client, pas
  comme une conformité automatique;
- dépendant de conditions de fait (la clé et le registre **restent** chez le
  client; aucune fuite de clé; pas de service hébergé — voir ADR 0002);
- valable **vis-à-vis du destinataire des substituts** (le fournisseur de LLM),
  pas vis-à-vis du client lui-même, pour qui les données restent personnelles
  puisqu'il détient la clé.

## 4. Risque résiduel de ré-identification par contexte

Même avec pseudonymisation réversible, un **risque résiduel de ré-identification
par contexte** subsiste (PRD §8 point 1): « Le dirigeant de la société de
menuiserie de Moulidars » reste identifiant même si le nom est substitué. Aucun
outil ne résout ça, et prétendre le contraire serait malhonnête. Ce risque est
documenté dans le README (§ limites) et l'ADR 0001 (dates par bucket de mois,
limites).

L'anonymisation au sens RGPD exigerait un critère de ré-identification très
élevé que la pseudonymisation réversible, par construction, ne peut garantir
(la clé rend la ré-identification possible pour son détenteur). anonyfy ne
prétend pas l'atteindre.

## 5. Responsabilité du DPO client

L'instruction du cas d'usage relève de la **responsabilité du DPO client** (ou
du conseil juridique qu'il mandate). anonyfy fournit:

- des **invariants techniques** documentés (clair ne quitte jamais l'infra
  client, déterminisme scopé, injectivité, rien démasqué qui n'ait été masqué);
- un **journal d'audit** exploititable par un DPO (empreinte HMAC-SHA-256,
  méta uniquement, jamais le texte — ADR 0001 §6-7);
- un **mode observation** (`anonyfy scan`) pour découvrir les spans détectés
  avant toute production.

Le DPO client reste responsable de:
- la **base légale** du traitement sous-jacent et de la transmission au
  sous-traitant (le fournisseur de LLM);
- la **gestion de la clé** dans un gestionnaire de secrets (ADR 0002 sur
  l'absence de service hébergé; `docs/MENACE.md` pour les contre-mesures,
  amorcé en phase 16);
- l'**analyse de risque** spécifique à ses données et au destinataire, tenant
  compte du risque résiduel de ré-identification par contexte;
- la **durée de conservation** du registre de scope (qui atteste l'appartenance
  des substituts et permet la réversibilité) et de sa purge en fin de besoin.

## 6. Références et limites de ce document

### 6.1 Références

- **RGPD** — Règlement (UE) 2016/679 du Parlement européen et du Conseil
  du 27 avril 2016, art. 4 (définitions : donnée personnelle,
  pseudonymisation), art. 32 (sécurité du traitement).
- **CJUE, *EDPS c. CRU***, septembre 2025 — approche relative de la
  notion de donnée personnelle pour des données pseudonymisées transmises
  à un destinataire sans moyen raisonnable de ré-identifier. Jurisprudence
  récente, encore discutée par le CEPD.
- **CEPD** (Comité européen de la protection des données) — lignes
  directrices sur la pseudonymisation et la notion de donnée personnelle;
  à instruire au cas par cas.
- **CNIL** — recommandations sur la pseudonymisation et les analyses
  d'impact (AIP) pour les traitements impliquant un sous-traitant (le
  fournisseur de LLM).
- **EDPB** (Comité européen de la protection des données, ex-Article 29
  WP) — avis sur l'anonymisation et la pseudonymisation.

### 6.2 Limite de ce document

Ce document est un **cadrage**, pas un avis juridique. La jurisprudence
(*EDPS c. CRU*) et les lignes directrices du CEPD évoluent; toute décision
d'usage repose sur la **propre analyse du client et de son conseil**. anonyfy
ne fournit pas de conseil juridique et n'engage aucune responsabilité sur
la qualification juridique d'un traitement. L'objectif reste l'honnêteté:
ne pas surpromettre « conforme RGPD » là où la réalité est plus nuancée et
plus intéressante (§2-3).

### 6.3 Documentation associée

- `README.md` — § « Ce que anonyfy ne fait pas » (limites §8).
- `docs/MENACE.md` — modèle de menace (gestion de clé + 4 menaces §8).
- `docs/ADR/0001-fpe-ff3.md` — décisions cryptographiques (empreinte
  HMAC, logging méta, dates bucket de mois, rotation de clé hors v1).
- `docs/ADR/0002-pas-de-service-heberge.md` — l'absence de service hébergé
  est une condition du raisonnement *EDPS c. CRU* (la clé et le registre
  restent chez le client).