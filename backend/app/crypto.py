"""Chiffrement au repos des secrets d'intégration.

Ce qui est chiffré ici, et pourquoi ça compte plus qu'un mot de passe applicatif :
un jeton d'accès Whoop donne accès à des mois de données physiologiques
continues — sommeil, fréquence cardiaque de repos, variabilité, séances. Une base
lue par un tiers, une sauvegarde qui traîne, un journal de requêtes trop bavard,
et ce sont ces données-là qui partent, pas seulement un accès à révoquer.

**La clé est dérivée de `JWT_SECRET`**, pas stockée séparément. Deux raisons, et une
conséquence à assumer :

- Un secret de plus à gérer est un secret de plus à oublier, et un déploiement qui
  démarre sans clé de chiffrement se met à écrire en clair sans que personne ne le
  voie. Ici, pas de clé = pas de démarrage, ce qui est déjà le cas de `JWT_SECRET`.
- La dérivation est HKDF-SHA256 avec un sel de contexte fixe : le jeton chiffré ne
  révèle rien sur le secret JWT, et compromettre l'un ne donne pas l'autre par
  simple lecture.
- **Conséquence** : changer `JWT_SECRET` rend les jetons illisibles. Ce n'est pas un
  défaut caché — `verify()` renvoie `None` plutôt que de lever, l'intégration
  demande une reconnexion, et le journal le dit. Une rotation de secret invalide de
  toute façon déjà toutes les sessions.
"""

from __future__ import annotations

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import settings

logger = logging.getLogger(__name__)

# Sel de contexte : il sépare cette dérivation de toute autre qui partirait du même
# secret. Fixe et public — c'est son rôle, un sel HKDF n'a pas à être secret.
_INFO = b"fuck-anxiety/oauth-tokens/v1"


def _key() -> bytes:
    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_INFO,
    ).derive(settings.jwt_secret.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def seal(plaintext: str) -> str:
    """Chiffre une valeur. Le résultat est du texte, stockable dans une colonne `text`."""
    return Fernet(_key()).encrypt(plaintext.encode("utf-8")).decode("ascii")


def unseal(ciphertext: str) -> str | None:
    """Déchiffre, ou `None` si la valeur est illisible.

    Ne lève pas : un jeton illisible (secret rompu, valeur corrompue) doit conduire à
    « reconnecte l'intégration », pas à une erreur 500 sur une route de lecture qui
    n'a rien à voir.
    """
    try:
        return Fernet(_key()).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        logger.warning(
            "Jeton d'intégration illisible : JWT_SECRET a probablement changé. "
            "Une reconnexion est nécessaire."
        )
        return None
