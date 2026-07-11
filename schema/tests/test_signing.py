"""Ed25519 signing over artifact.digest (ROADMAP item 2 / SPEC §5 'future')."""

import pytest
from just_dna_format.integrity import IntegrityError, verify_signature
from just_dna_format.signing import (
    generate_private_key_pem,
    public_key_b64_from_pem,
    sign_digest,
)

_DIGEST = "sha256:" + "ab" * 32


def test_sign_verify_roundtrip() -> None:
    pem = generate_private_key_pem()
    sig = sign_digest(_DIGEST, pem)
    assert sig.algorithm == "ed25519"
    verify_signature(_DIGEST, sig)  # self-consistent
    verify_signature(_DIGEST, sig, trusted_public_key=public_key_b64_from_pem(pem))


def test_tampered_digest_fails() -> None:
    sig = sign_digest(_DIGEST, generate_private_key_pem())
    with pytest.raises(IntegrityError, match="invalid"):
        verify_signature("sha256:" + "cd" * 32, sig)


def test_wrong_pinned_key_rejected() -> None:
    pem_a, pem_b = generate_private_key_pem(), generate_private_key_pem()
    sig = sign_digest(_DIGEST, pem_a)
    with pytest.raises(IntegrityError, match="pinned"):
        verify_signature(_DIGEST, sig, trusted_public_key=public_key_b64_from_pem(pem_b))


def test_public_key_matches_signer() -> None:
    pem = generate_private_key_pem()
    sig = sign_digest(_DIGEST, pem)
    assert sig.public_key == public_key_b64_from_pem(pem)


def test_unsupported_algorithm_rejected() -> None:
    sig = sign_digest(_DIGEST, generate_private_key_pem())
    sig.algorithm = "rsa"
    with pytest.raises(IntegrityError, match="unsupported signature algorithm"):
        verify_signature(_DIGEST, sig)
