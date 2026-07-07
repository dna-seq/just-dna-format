"""
Ed25519 signing over `artifact.digest` (SPEC §5 "future") — the private-key / key-management side.

The artifact digest is already the version's immutable content identity, so signing it — rather
than any larger blob — is enough to bind a trusted party's key to the whole file set. A client
that pins the marketplace's public key can then detect a digest swapped by a compromised storage
backend. Signing is entirely optional and additive: an unsigned manifest verifies exactly as
before.

Verification lives in `integrity.verify_signature` (verification is integrity's job, and keeping
it there avoids an import cycle). Keys are handled as PEM on the private side (what an operator
stores) and as raw base64 on the public side (what travels in the manifest, small and
self-contained).
"""

import base64
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from just_dna_format.integrity import IntegrityError
from just_dna_format.manifest import Signature

_ALGORITHM: str = "ed25519"


def _load_private_key(private_key_pem: bytes) -> ed25519.Ed25519PrivateKey:
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise IntegrityError("signing key is not an Ed25519 private key")
    return key


def _public_key_b64(public_key: ed25519.Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return base64.b64encode(raw).decode("ascii")


def public_key_b64_from_pem(private_key_pem: bytes) -> str:
    """The base64 raw Ed25519 public key derived from a PEM private key — what a server publishes."""
    return _public_key_b64(_load_private_key(private_key_pem).public_key())


def generate_private_key_pem() -> bytes:
    """Generate a fresh Ed25519 private key as unencrypted PKCS#8 PEM (for tests / key bootstrap)."""
    key = ed25519.Ed25519PrivateKey.generate()
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def sign_digest(
    digest: str, private_key_pem: bytes, *, signed_at: Optional[str] = None
) -> Signature:
    """Sign the `artifact.digest` string with an Ed25519 PEM private key.

    The signed message is the digest string's UTF-8 bytes (e.g. `b"sha256:9f2c...ab"`)."""
    key = _load_private_key(private_key_pem)
    sig = key.sign(digest.encode("utf-8"))
    return Signature(
        algorithm=_ALGORITHM,
        public_key=_public_key_b64(key.public_key()),
        signature=base64.b64encode(sig).decode("ascii"),
        signed_at=signed_at,
    )
