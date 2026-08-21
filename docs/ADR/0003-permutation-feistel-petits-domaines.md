# ADR 0003 — Permutation keyée Feistel pour les petits domaines non-FPE

Statut: Accepté · Date: Août 2026 · Phase: 13 (M2)

Décision cryptographique pour la réversibilité des types non-FPE
(patronyme, prénom, commune, voie, plaque SIV, référence de dossier,
date, email local-part) sans stocker de valeur claire. Références:
`.olgenius/DECISIONS.md` D22, D23, D24, D26; `docs/ADR/0001-fpe-ff3.md`
§4 (FPE par type), §13 (rotation de clé hors périmètre v1).

---

## 1. Contexte

Le plan et l'ADR 0001 (D2 « mécanisme registre », D4 « jamais de clair
stocké ») spécifiaient que les types à petit domaine (plaque SIV,
référence de dossier, patronymes, dates, emails) ne passent pas par FPE
pur FF3-1. En revanche, ils ne précisaient pas **comment rendre `unmask`
réversible pour ces types sans stocker le clair**.

Le problème: la sélection gazetteer de la phase 11 (`pick`) utilise
`HMAC(key, scope || type || clair) mod N`, qui n'est **pas bijective**
(preimage infaisable) → non réversible. Le registre de scope (phase 10)
crée une injection clair → slot mais ne permet pas de remonter
slot → clair sans stocker le clair (interdit par l'invariant 1 et D4).

FF3-1 lui-même est écarté pour ces domaines (D2): FF3-1 est faible sur
petits domaines, son alphabet fixe (radix 40) est inadapté à l'email
local-part (apostrophes, accents), et le minimum de domaine FF3-1 n'est
pas respecté (plaque SIV ~1000 valeurs).

---

## 2. Options envisagées

- **(a) Permutation keyée inversible** — réseau de Feistel + cycle-walking,
  round function HMAC-SHA256, stdlib `hmac`/`hashlib` uniquement, isolée
  dans `src/anonyfy/surrogate/permutation.py` (analogue à l'isolation
  `ff3` dans `surrogate/fpe.py`). Le registre garde son rôle d'appartenance
  (invariant 4) + injectivité scopée + compensation des collisions. La
  réversibilité vient de la permutation inversible, pas du registre.
- **(b) Registre stocke le clair chiffré** — envelope encryption sous la clé.
  Réversibilité triviale, mais contredit D4 (« contenu non chiffré, jamais
  de clair ») et PRD §8 point 2 (« jamais de clair stocké », raison du
  report de la rotation de clé T1 en v2). Sort de l'invariant 1.
- **(c) Réutiliser `ff3` (FF3-1)** — contredit D2 (« pas FPE pur pour petit
  domaine »), alphabet fixe inadapté, minimum de domaine non respecté.
- **(d) Reporter les types non-FPE hors v1** — réduction de périmètre au
 -delà du PRD validé (plus de pseudonymisation noms/adresses/dates).

---

## 3. Décision

**Option (a), validée par l'utilisateur** (escalade sécurité Olgenius §7).

La permutation keyée Feistel + cycle-walking est une **construction FPE
standard** (FF1/FFX-like). La bijectivité est prouvée par test exhaustif
sur tous les petits domaines (plaque 1000, date ~84k, gazetteers 2k-34k)
+ round-trip + indépendance de la clé. Stdlib uniquement (`hmac`/`hashlib`),
zéro nouvelle dépendance, cohérent avec le principe « dépendances minimales ».

### 3.1 Module

`src/anonyfy/surrogate/permutation.py` (primitive inversible, isolée).
Cinq encrypt/decrypt par type non-FPE:

| Type | Domaine | Construction |
|---|---|---|
| Gazetteer (patronyme, prénom, commune, voie) | 2 000-34 000 | Permutation sur index gazetteer |
| Plaque SIV | ~1000 (chiffres) | Permutation sur [0, 1000), lettres préservées |
| Référence de dossier | Domaine générique non énumérable | XOR keystream HMAC sur UTF-8 |
| Email local-part | Alphabet local-part effectif (D9) | Permutation sur alphabet, longueur préservée, domaine en clair, repli keystream pour local-part trop courte |
| Date | [0, 67536) (201 ans x 12 mois x 28 jours) | Permutation avec jour clampé [1, 28] (D8 bucket de mois) |

### 3.2 Rôle du registre

Le registre de scope (phase 10) reste le seul état persistant. Il
garantit:

- **l'appartenance** (invariant 4): `unmask` ne déchiffre que les substituts
  présents au registre;
- **l'injectivité scopée** (invariant 3): deux valeurs claires distinctes
  ne partagent jamais un substitut dans un scope;
- **la compensation des collisions**: si la permutation produit un
  substitut déjà émis, le registre lève `RegistryError` (protection non
  silencieuse de l'invariant 3).

La **réversibilité** vient de la permutation inversible, pas du registre.
Le registre ne stocke jamais le clair (D4, invariant 1).

---

## 4. Points fixes (D23)

Une permutation bijective a nécessairement des points fixes
(Feistel != derangement): `encrypt(x) == x` pour certains clairs. Le
masquage **détecte** si `sub == clair` (point fixe) et **journalise un
avertissement + lève une alerte** (jamais silencieux).

**Limite documentée**: fuite résiduelle rare (probabilité ~ 1/N par
clair, N = taille du gazetteer/domaine, soit 0,03 %-0,5 %). En production,
un clair point fixe est détectable (`sub == clair`) et traitable (re-key
ou traitement manuel). La grande majorité des clairs du corpus de test
(Jean, Dupont, etc.) ne sont **pas** points fixes avec la clé de test
`b'0'*16`.

**Garde-fou conditionnel**: si un clair du corpus est point fixe avec
`b'0'*16` et bloque un critère exécutable, le masquage monte au sondage
registre + offset (garantie derangement: `index_sub = (pi(index_clair) + k)
mod N` par sondage sautant les points fixes et collisions, offset `k`
stocké dans le registre — pas le clair, conforme invariant 1). Cette
garantie est réversible, bijective scopée et conforme invariant 1.

---

## 5. Préservation de la casse (D24)

Le round-trip perd la casse: `mask("Marc Leroy")` produit un substitut
majuscule (gazetteer SIRENE en MAJUSCULES); `unmask` restitue la forme
canonique du gazetteer → "MARC LEROY" au lieu de "Marc Leroy".

**Décision**: un **flag casse** (LC/TC/UC/MX, métadonnée non-clair, 2 bits)
est stocké dans le registre. Au masquage, le pattern de casse du clair est
détecté et stocké. À l'unmask, le nom gazetteer (majuscule) est restitué
avec le flag appliqué. Round-trip exact pour casse LC/TC/UC.

Extension registre: colonne `case_pattern` (TEXT, valeurs 'LC'/'TC'/'UC'/'MX'),
schema_version bump.

**Limite résiduelle**: casse « mixed » (ex. "McDonald") non fidèlement
restituable par un flag 3-4 valeurs → repli sur Title Case, documenté.

---

## 6. Date bucket de mois (D8)

La permutation porte sur [0, 67536) (201 ans x 12 mois x 28 jours), avec
jour clampé à [1, 28] avant encodage (28 existe dans tous les mois →
réversibilité garantie pour jour <= 28). Jour > 28 clampé: perte
documentée (D8 « précision jour non préservée »). Le substitut est une
date valide dans [1900-01-01, 2100-12-31], format préservé.

La date substituée reste **ré-identifiable par contexte** (PRD §8 point 1):
le décalage ne prétend pas l'empêcher. Documenté dans le README (§8) et
l'ADR 0001 §10.

---

## 7. Collision inter-type PRENOM/PATRONYME (D26)

`used_surrogates` est global au scope (pas par `entity_type`). Les ciphers
gazetteer PATRONYME et PRENOM puisent leurs substituts dans leurs
gazetteers respectifs (SIRENE pour noms, INSEE pour prenoms) qui se
chevauchent (242 noms communs sur 5000). Quand un substitut émis pour
PRENOM est un nom commun (ex. TOUSSAINT) et qu'un PATRONYME ultérieur
produit le même substitut par permutation, le registre global détecte la
collision et lève `RegistryError`.

**Limite connue v1**: la collision inter-type est rare en production
(texte avec prénom pur + patronyme collisionnant dans le même scope).
`RegistryError` protège explicitement l'invariant 3 (pas de violation
silencieuse de l'injectivité).

**Workaround v1**: re-key ou re-scope le texte en collision (le
`RegistryError` est non silencieux et invite l'opérateur à relancer).

**Solution v2**: sondage registre + offset. Le cipher interroge le
registre avant d'émettre un substitut; si collision, il compose le
substitut avec un offset (ou sélectionne un autre point du cycle-walking)
pour garantir l'unicité globale sans casser la bijectivité scopée. Cela
nécessite d'étendre `register_fpe` pour accepter un substitut candidat et
le résoudre en cas de conflit, et de rendre le cipher itératif sur le
cycle-walking jusqu'à trouver un substitut libre.

---

## 8. Risque résiduel

Crypto maison non prouvée par vecteurs NIST (D6 visait FF3-1 sur grands
domaines, inapplicable aux petits domaines où FF3-1 est écarté par D2).
Mitigation: test exhaustif de bijectivité + déterminisme scopé +
indépendance de la clé + round-trip sur tous les petits domaines; cet
ADR documente la posture (FPE petit-domaine, justification de l'absence
de vecteurs NIST).

---

## 9. Conséquences

- Nouveau module `src/anonyfy/surrogate/permutation.py` (primitive
  inversible, isolation analogue à `ff3` dans `fpe.py`).
- Cinq encrypt/decrypt par type non-FPE (gazetteer, plaque SIV, référence
  XOR keystream, email local-part, date).
- `pick` (phase 11) conservé pour référence/tests (non réversible).
- Le registre stocke un flag casse (D24) et lève `RegistryError` sur
  collision inter-type (D26), sans jamais stocker le clair (invariant 1).
- La rotation de clé (ADR 0001 §13) reste hors périmètre v1: la
  permutation keyée dépend de la clé, et toute rotation exigerait de
  rejouer les indices, impossible sans le clair (interdit par invariant 1).