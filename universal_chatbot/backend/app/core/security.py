import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from universal_chatbot.backend.app.core.config import chatbot_settings

# Derive a 256-bit encryption key
_derived_aes_key = hashlib.sha256(chatbot_settings.PLATFORM_ENCRYPTION_KEY.encode()).digest()
_aesgcm = AESGCM(_derived_aes_key)


def encrypt_secret(plain_text: str) -> str:
    """Encrypt a secret string (e.g. database password or API key) using AES-256-GCM."""
    if not plain_text:
        return ""
    nonce = os.urandom(12)
    cipher_bytes = _aesgcm.encrypt(nonce, plain_text.encode("utf-8"), None)
    return base64.b64encode(nonce + cipher_bytes).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    """Decrypt an AES-256-GCM encrypted secret string."""
    if not cipher_text:
        return ""
    try:
        raw = base64.b64decode(cipher_text.encode("utf-8"))
        nonce = raw[:12]
        cipher_bytes = raw[12:]
        decrypted = _aesgcm.decrypt(nonce, cipher_bytes, None)
        return decrypted.decode("utf-8")
    except Exception:
        return ""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _b64url_decode(data_str: str) -> bytes:
    padding = "=" * (4 - (len(data_str) % 4)) if len(data_str) % 4 else ""
    return base64.urlsafe_b64decode((data_str + padding).encode("utf-8"))


def create_admin_jwt(payload: Dict[str, Any], expires_in_seconds: int = 86400) -> str:
    """Create a signed JWT token (HS256) for admin authentication."""
    data = payload.copy()
    data["exp"] = int(time.time()) + expires_in_seconds
    data["iat"] = int(time.time())

    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(data, separators=(",", ":")).encode("utf-8"))
    msg = f"{header_b64}.{payload_b64}".encode("utf-8")
    sig = hmac.new(chatbot_settings.CHATBOT_SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_admin_jwt(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode an admin JWT token."""
    return verify_integration_token(token, chatbot_settings.CHATBOT_SECRET_KEY)


def verify_integration_token(token: str, app_secret: str) -> Optional[Dict[str, Any]]:
    """
    Verify host application integration token (HS256).
    Returns verified claims dict (containing tenant_id, website_id, user_id) or None.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        msg = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(app_secret.encode("utf-8"), msg, hashlib.sha256).digest()
        provided_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        if "exp" in payload and payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


def verify_hmac_signature(payload_bytes: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature for backend-to-backend webhooks or API requests."""
    try:
        expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False
