"""Per-node identity key management for interop signing."""

from __future__ import annotations

from base64 import b64encode
from pathlib import Path


def ensure_identity_keys(secrets_dir: Path) -> dict[str, str] | None:
    private_path = secrets_dir / "interop_signing_private_key.pem"
    public_path = secrets_dir / "interop_signing_public_key.pem"
    public_b64_path = secrets_dir / "interop_signing_public_key.b64"
    if private_path.exists() and public_path.exists() and public_b64_path.exists():
        return {
            "private_key_path": str(private_path),
            "public_key_path": str(public_path),
            "public_key_b64_path": str(public_b64_path),
        }
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        return None
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    public_b64_path.write_text(b64encode(public_raw).decode("utf-8") + "\n", encoding="utf-8")
    return {
        "private_key_path": str(private_path),
        "public_key_path": str(public_path),
        "public_key_b64_path": str(public_b64_path),
    }
