# Corpus synthétique de non-régression

Ce corpus contient des textes **synthétiques** (construits, sans données
personnelles réelles) destinés aux tests de **non-régression**: déterminisme,
round-trip (`unmask(mask(x)) == x`), injectivité (zéro collision), et absence de
fuite du clair.

Il n'est **pas** utilisé pour mesurer le rappel (décision D12): les validateurs
sont conçus pour ces identifiants, le rappel serait mécaniquement ~100 % et
constituerait une surpromesse. Le rappel 98 % se mesure contre le corpus réel
annoté (voir `../corpus_real/README.md`).

## Contenu

Chaque fichier `doc_NNN.txt` contient un texte synthétique couvrant un ou
plusieurs types d'identifiants français:

- NIR, SIREN, SIRET, IBAN, TVA, carte bancaire, téléphone (structurés FPE);
- plaque SIV, référence de dossier;
- date (jour ≤ 28 pour réversibilité, D8);
- email (forme régularisée: minuscules, accents, apostrophes, points
  multiples, longueur 64 — D9);
- patronyme et prénom en contexte déclenché (« M. », « né(e) le »,
  « demeurant »);
- commune et voie (en contexte déclenché « demeurant »).

Les annotations (types et positions des identifiants) sont **connues par
construction**. Aucun fichier `.ann.jsonl` n'est nécessaire pour le test de
non-régression; le round-trip valide la réversibilité sans annotation externe.

## Utilisation

```
uv run pytest tests/acceptance/test_roundtrip_full.py -k synthetic
```