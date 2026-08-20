"""Anonyfy - anonymisation réversible par pseudonymisation.

Paquet Python de pseudonymisation réversible d'identifiants personnels français
(structurés et non structurés) pour l'envoi à un modèle de langage, avec
registre de scope garantissant la réversibilité.

Phase 08 - API publique ``Vault``: masquage/démasquage des identifiants
structurés à grand domaine (NIR, SIREN, SIRET, IBAN, TVA, CB, téléphone) par FPE
avec registre de scope et intégration Aho-Corasick.
"""

from anonyfy.vault import Vault

__version__ = "0.1.0"

__all__ = ["Vault", "__version__"]
