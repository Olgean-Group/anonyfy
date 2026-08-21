# Tutoriel d'intégration anonyfy

> Guide d'intégration détaillé. À lire après le README (installation,
> positionnement juridique, limites). Statut: v0.1 · Août 2026.

Ce tutoriel couvre les cas d'usage principaux: création d'un Vault, scan
d'un texte (mode observation), masquage/démasquage aller-retour, politique
`permissive` / `strict`, `mask_json` / `unmask_json`, journal d'audit et
rapport DPO, et CLI.

---

## 1. Installation

```bash
uv add anonyfy
```

Python >= 3.11. Le cœur ne dépend que de la bibliothèque standard et de
`ff3` (FPE FF3-1, isolé derrière `surrogate/fpe.py`, voir ADR 0001).
Aucun téléchargement de modèle, fonctionne hors ligne.

---

## 2. Le Vault — clé, scope, registre

Le `Vault` est le point d'entrée de l'API publique. Trois paramètres sont
obligatoires:

- `key`: clé FPE (16, 24 ou 32 bytes). **La clé est la racine du montage**
  (PRD §8 point 3): sa fuite compromet tous les substituts du scope. Elle
  doit vivre dans un gestionnaire de secrets, jamais dans le dépôt, jamais
  dans le journal. Voir `docs/MENACE.md`.
- `scope`: identifiant de scope (chaîne). Le déterminisme est scopé
  (invariant 2): une même valeur produit le même substitut dans un scope,
  des substituts différents entre scopes.
- `registry_path`: chemin du registre SQLite persistant. Le registre
  atteste l'appartenance des substituts (invariant 4) et garantit
  l'injectivité scopée (invariant 3). **Il ne stocke jamais de clair**
  (D4, invariant 1).

```python
import secrets
from anonyfy import Vault

key = secrets.token_bytes(16)  # 16 bytes; ne jamais hardcoder
v = Vault(
    key=key,
    scope="dossier-1234",
    registry_path="/var/lib/anonyfy/dossier-1234.db",
)
```

Le registre est persistant: unmask fonctionne après redémarrage du
processus, tant que le fichier `.db` est conservé et que la clé et le
scope sont identiques. La version du gazetteer est vérifiée au unmask
(`GazetteerVersionMismatch` si l'empreinte diffère de celle du registre,
D5).

---

## 3. scan — mode observation (détecte, ne modifie rien)

Le mode observation (PRD F7) détecte les identifiants, les journalise et
**ne modifie rien**. C'est la condition d'adoption: personne ne met
anonyfy dans le chemin critique sans avoir vu d'abord ce qui aurait été
remplacé.

```python
v = Vault(key=key, scope="dossier-1234", registry_path=chemin)
obs = v.mask("M. Jean Dupont, SIRET 73282932000033", observe=True)
assert obs.text == "M. Jean Dupont, SIRET 73282932000033"  # inchangé
for e in obs.entities:
    print(e.type, e.value, e.rule_id, e.confidence)
```

En mode observation, `.text` est l'original et `.entities` contient les
spans détectés (non substitués, avec leur confidence et `rule_id`). Le
registre n'est pas peuplé.

---

## 4. mask / unmask — aller-retour

```python
texte = "M. Jean Dupont, né le 3 mai 1990, SIRET 73282932000033"
m = v.mask(texte)
# m.text ne contient ni "Jean", ni "Dupont", ni "73282932000033"
assert "73282932000033" not in m.text
assert "Jean" not in m.text

# Le modèle reçoit m.text, produit une réponse qui cite les substituts.
reponse_modele = m.text + " — dossier validé."

# unmask restitue le texte clair.
clair = v.unmask(reponse_modele)
assert "73282932000033" in clair
assert "Jean" in clair
```

### Invariant 4 — rien n'est démasqué qui n'ait été masqué

`unmask` ne transforme que des substituts réellement émis dans le scope.
Un identifiant valide **jamais émis** (inventé par le modèle) reste tel
quel: il n'est pas déchiffré en une fausse valeur claire.

```python
# Un SIRET valide jamais émis dans le scope n'est pas déchiffré.
intrusion = v.unmask("SIRET 41804261100032")
assert "41804261100032" in intrusion  # laissé inchangé
```

### Aho-Corasick — reformattage par le modèle

Le modèle peut reformater les substituts (SIRET groupé par 3, « M. Leroy »
au lieu de « Marc Leroy »). L'automate Aho-Corasick (phase 10b) retrouve
les substituts reformatés et `unmask` restitue l'original.

```python
m = v.mask("SIRET 73282932000033")
reformate = m.text.replace("73282932000033", "732 829 320 000 35")
assert v.unmask(reformate) == "SIRET 73282932000033"
```

### Cohérence des offsets `.entities`

Après `mask`, les offsets de `.entities` pointent vers les substituts
réels dans `.text` (y compris si le substitut est plus long ou plus court
que l'original, D15). Utile pour aligner des annotations externes.

```python
m = v.mask("SIRET 73282932000033")
for e in m.entities:
    assert m.text[e.start:e.end] == e.value  # pointe vers le substitut réel
```

---

## 5. Politique de fermeture — permissive / strict

Le `Vault` accepte un paramètre `policy` (défaut `permissive`, PRD F8).

- **`permissive`** (défaut): un span de confiance faible non confirmé par
  contexte (confidence < 0.8, sans déclencheur contextuel) est substitué
  comme les autres; un avertissement méta-only est journalisé (si un
  `AuditLog` est fourni). Aucune régression par rapport aux versions
  antérieures.
- **`strict`**: un span de confiance faible non confirmé lève
  `UnresolvedSpanError` avant substitution.

```python
from anonyfy import Vault
from anonyfy.vault import UnresolvedSpanError

v = Vault(key=key, scope="s", registry_path=chemin, policy="strict")
try:
    v.mask("Boulangerie Pierre fait du pain")  # "Pierre" sans déclencheur
    raise AssertionError("devrait lever UnresolvedSpanError")
except UnresolvedSpanError:
    pass
```

Le seuil `WEAK_CONFIDENCE_THRESHOLD = 0.8` est une constante publique dans
`vault.py`. Un span avec déclencheur contextuel fort (`M.`, `né(e) le`,
`demeurant`) a confidence 0.9 (>= 0.8, confirmé); sans déclencheur,
confidence 0.5 (< 0.8, faible).

---

## 6. mask_json / unmask_json — primitive, pas un proxy

`mask_json` / `unmask_json` parcourent l'arbre JSON et ne masquent que les
feuilles chaîne, jamais les clés, jamais les valeurs structurelles, jamais
`function.name`. Une politique d'exemption par chemin (`$.path.glob`)
exempte des sous-arbres entiers.

```python
import json
v = Vault(key=key, scope="s", registry_path=chemin)
payload = {
    "model": "gpt-4",
    "tools": [
        {
            "function": {
                "name": "chercher_client",
                "parameters": {"text": "M. Jean Dupont, SIRET 73282932000033"},
            }
        }
    ],
}
masque = v.mask_json(
    payload,
    exempt=["$.tools[*].function.name", "$.model"],
)
assert masque["model"] == "gpt-4"
assert masque["tools"][0]["function"]["name"] == "chercher_client"
assert "Jean" not in json.dumps(masque)

# Round-trip JSON.
assert v.unmask_json(masque) == payload
```

**`mask_json` est une primitive, pas un proxy** (OBJ-025). Le proxy
compatible OpenAI (PRD §4 v2) n'est pas livré en v1; `mask_json` expose
déjà la primitive de parcours pour que l'intégrateur puisse câbler le
masquage de payloads structurés en attendant le proxy.

---

## 7. Journal d'audit et rapport DPO

### Journal d'audit

Le journal est JSON lines. **Méta uniquement** (D10): scope, compte par
type, règle déclenchée, empreinte HMAC-SHA-256(key, texte) (D3). Ni le
clair ni les substituts ne sont jamais écrits.

```python
from anonyfy.audit import AuditLog

log = AuditLog("/var/log/anonyfy/audit.jsonl")
v = Vault(key=key, scope="s", registry_path=chemin, audit=log)
v.mask("M. Jean Dupont, SIRET 73282932000033")

contenu = open("/var/log/anonyfy/audit.jsonl").read()
assert "Jean" not in contenu           # pas de clair
assert "Dupont" not in contenu          # pas de clair
assert "73282932000033" not in contenu  # pas de clair
# Le journal ne contient que des méta (scope, types, empreinte HMAC).
```

L'empreinte est HMAC-SHA-256(key, texte), pas SHA-256 (qui serait
inversible par dictionnaire, D3). Deux textes identiques sous deux clés
différentes donnent deux empreintes différentes.

### Rapport DPO

`Vault.report()` produit une synthèse lisible par un non-développeur:
types rencontrés, volumes, règles actives, version du gazetteer.

```python
v.mask("SIRET 73282932000033 et M. Jean Dupont")
r = v.report()
assert "SIRET" in r
assert "gazetteer" in r.lower()
```

---

## 8. CLI — scan, mask, unmask

La CLI utilise stdlib `argparse` (zéro dépendance supplémentaire). La clé
ne peut provenir que de `ANONYFY_KEY` (hex) ou de `--key-file` (mode 0600);
`--key` en clair est refusé (visible via `ps`).

### scan — mode observation, ne modifie pas l'entrée

```bash
ANONYFY_KEY=00000000000000000000000000000000 \
  uv run anonyfy scan fichier.txt --scope dossier-1234 --out rapport.txt
```

`scan` produit un rapport; le fichier d'entrée n'est pas modifié.

### mask — masque et écrit dans --out

```bash
echo "SIRET 73282932000033" > /tmp/in.txt
ANONYFY_KEY=00000000000000000000000000000000 \
  uv run anonyfy mask /tmp/in.txt --scope s --registry /tmp/reg.db --out /tmp/out.txt
```

### unmask — restitue le clair (deuxième invocation)

```bash
ANONYFY_KEY=00000000000000000000000000000000 \
  uv run anonyfy unmask /tmp/out.txt --scope s --registry /tmp/reg.db --out /tmp/restored.txt
```

Le round-trip fonctionne en deux invocations séparées (cross-process)
tant que le `--scope` et le `--registry` sont identiques.

### Sécurité de la clé (D11)

- `--key-file` refuse un fichier dont le mode autorise groupe ou autre
  (`st_mode & 0o077 != 0`). Mode attendu: 0600 ou 0400.
- Un avertissement est affiché si la clé provient de `ANONYFY_KEY`
  (héritée par les sous-processus). En production, préférez `--key-file`
  ou purgez l'environnement (`env -u ANONYFY_KEY`).

Voir `docs/MENACE.md` pour le modèle de menace complet sur la gestion de
clé.

---

## 9. Types couverts (v1)

| Type | Mécanisme | Remarque |
|---|---|---|
| NIR, SIREN, SIRET, IBAN, TVA, CB, téléphone | FPE FF3-1 (grand domaine) | Clé de contrôle recalculée |
| Email | FPE local-part (normalisation NFKC + minuscules, D9) | Domaine gazetteer |
| Plaque SIV, référence de dossier | Mécanisme registre (petit domaine, D2) | Permutation keyée (D22) |
| Patronyme, prénom, commune, voie | Gazetteer + permutation keyée (D22) | Caisse préservée par flag registre (D24) |
| Date | Permutation sur bucket de mois (D8) | Précision jour non préservée |

---

## 10. Limites à connaître avant d'intégrer

Ces limites sont volontaires et documentées. Les dissimuler discréditerait
l'outil. Voir `README.md` § « Ce que anonyfy ne fait pas » et
`docs/MENACE.md`.

- **Pseudonymisation, pas anonymisation** au sens RGPD. Voir
  `docs/JURIDIQUE.md`.
- **Ré-identification par contexte** (§8 point 1): un substitut peut
  ré-identifier si le contexte autour est unique.
- **Dictionnaire de code** (§8 point 2): un mapping déterministe est un
  code book; mitigation par clé secrète et sel par scope.
- **Compromission de la clé** (§8 point 3): la clé permet de tout inverser.
- **FPE sur petits domaines** (§8 point 4): bijectivité mais points fixes
  (D23, probabilité ~1/N, détectés et alertés).
- **Date bucket de mois** (D8): ré-identifiable par contexte.
- **Rotation de clé hors v1**: reportée à v2 (exigerait un registre
  stockant du clair, interdit par invariant 1).
- **Cohérence inter-type SIREN/SIRET/TVA** non garantie (OBJ-008).
- **Collision inter-type PRENOM/PATRONYME** (D26): `RegistryError` rare;
  workaround re-key, solution v2 sondage.
- **`mask_json` est une primitive, pas un proxy** (OBJ-025).

---

*Voir `docs/ADR/` pour les décisions architecturales figées et
`.olgenius/PLAN.md` pour le plan d'exécution complet.*