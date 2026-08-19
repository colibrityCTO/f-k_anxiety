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

from .config import settings

logger = logging.getLogger(__name__)


class Unavailable(RuntimeError):
    """`cryptography` n'est pas installée : l'intégration est indisponible."""


def available() -> bool:
    """La bibliothèque est-elle là ?

    Sert à décider si une intégration se propose ou non, plutôt qu'à la laisser
    échouer au premier clic.
    """
    try:
        import cryptography.fernet  # noqa: F401

        return True
    except ImportError:
        return False

# Sel de contexte : il sépare cette dérivation de toute autre qui partirait du même
# secret. Fixe et public — c'est son rôle, un sel HKDF n'a pas à être secret.
_INFO = b"fuck-anxiety/oauth-tokens/v1"


def _key() -> bytes:
    """Import **dans la fonction**, et c'est la leçon de l'incident.

    Ce module importait `cryptography` au niveau du module. Comme
    `integrations/whoop.py` importe `crypto`, que `routers/integrations.py` importe
    `whoop`, et que `main.py` importe le routeur, une dépendance absente faisait
    échouer l'import de l'application entière : uvicorn ne démarrait pas, et le
    healthcheck échouait sans autre explication.

    Le reste du projet avait déjà la bonne convention — `push.py` importe
    `pywebpush` dans un `try/except ImportError` et désactive les notifications,
    `vapid.py` importe `cryptography` dans sa fonction. La convention est reprise
    ici. Une intégration de bracelet ne doit pas pouvoir empêcher quelqu'un
    d'enregistrer son check-in.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    derived = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_INFO,
    ).derive(settings.jwt_secret.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def seal(plaintext: str) -> str:
    """Chiffre une valeur. Le résultat est du texte, stockable dans une colonne `text`."""
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - dépendance absente
        raise Unavailable(
            "La bibliothèque de chiffrement n'est pas installée sur ce serveur : "
            "impossible de stocker un jeton d'intégration en sécurité."
        ) from exc
    return Fernet(_key()).encrypt(plaintext.encode("utf-8")).decode("ascii")


def unseal(ciphertext: str) -> str | None:
    """Déchiffre, ou `None` si la valeur est illisible.

    Ne lève pas : un jeton illisible (secret rompu, valeur corrompue) doit conduire à
    « reconnecte l'intégration », pas à une erreur 500 sur une route de lecture qui
    n'a rien à voir.
    """
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:  # pragma: no cover - dépendance absente
        logger.error("Bibliothèque de chiffrement absente : intégrations désactivées")
        return None
    try:
        return Fernet(_key()).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        logger.warning(
            "Jeton d'intégration illisible : JWT_SECRET a probablement changé. "
            "Une reconnexion est nécessaire."
        )
        return None
