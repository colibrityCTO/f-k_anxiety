"""Génération d'une paire de clés VAPID.

    python -m app.vapid

Colle les deux lignes affichées dans `backend/.env`. La clé publique est aussi
servie par `GET /push/key` : le navigateur en a besoin pour s'abonner.

Ne régénère pas la paire une fois des abonnements enregistrés — les abonnements
existants seraient tous invalidés d'un coup.
"""

from __future__ import annotations

import base64


def generate() -> tuple[str, str]:
    """Retourne (clé publique, clé privée) en base64url sans remplissage."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    private = ec.generate_private_key(ec.SECP256R1())
    private_bytes = private.private_numbers().private_value.to_bytes(32, "big")
    public_bytes = private.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )

    def encode(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return encode(public_bytes), encode(private_bytes)


def main() -> int:
    public, private = generate()
    print("# Notifications push — à coller dans backend/.env")
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    print("VAPID_SUBJECT=mailto:toi@exemple.fr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
