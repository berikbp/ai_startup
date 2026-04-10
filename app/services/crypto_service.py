from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings


class CryptoService:
    def __init__(self, settings: Settings):
        key_material = settings.resolved_telegram_token_encryption_key.encode("utf-8")
        self._key = hashlib.sha256(key_material).digest()

    def encrypt(self, value: str) -> str:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, value.encode("utf-8"), None)
        payload = nonce + ciphertext
        return base64.urlsafe_b64encode(payload).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            payload = base64.urlsafe_b64decode(value.encode("ascii"))
        except Exception as exc:  # pragma: no cover - guarded by caller behavior
            raise ValueError("Encrypted payload is not valid base64.") from exc

        if len(payload) <= 12:
            raise ValueError("Encrypted payload is too short.")

        nonce = payload[:12]
        ciphertext = payload[12:]
        plaintext = AESGCM(self._key).decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
