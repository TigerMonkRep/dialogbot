"""Print a new VAPID key pair for Web Push: python -m scripts.generate_vapid

Put the values in the API and worker environment (Render) – never in the repository:
  VAPID_PUBLIC_KEY   base64url, uncompressed P-256 point (the browser's applicationServerKey)
  VAPID_PRIVATE_KEY  base64url, raw 32-byte private key (what pywebpush/py-vapid accept)
  VAPID_SUBJECT      mailto:… or https://… contact for the push services
Changing the pair makes every existing subscription invalid (browsers must subscribe again).
"""
from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def generate() -> tuple[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return _b64(public), _b64(private)


def main() -> int:
    public, private = generate()
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    print("VAPID_SUBJECT=mailto:info@dialogbot.dk")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
