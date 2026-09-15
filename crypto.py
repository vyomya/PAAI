"""
Symmetric encryption for OAuth tokens at rest.

Once PAAI is multi-user you are holding other people's Gmail/Outlook refresh
tokens. A refresh token is a long-lived key to someone's entire mailbox, so it
does not go into the database in plaintext.

This is the minimum bar. The stronger option is AWS Secrets Manager or Azure
Key Vault holding the tokens themselves, with only a reference stored in
Postgres — worth doing before you have real users, but this unblocks Phase 1.
"""
from cryptography.fernet import Fernet, InvalidToken

from config import settings


class TokenCipher:
    def __init__(self, key: str | None = None):
        key = key or settings.encryption_key
        if not key:
            raise RuntimeError(
                "ENCRYPTION_KEY is not set. Generate one with:\n"
                '  python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            )
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str | None) -> bytes | None:
        if plaintext is None:
            return None
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes | None) -> str | None:
        if ciphertext is None:
            return None
        try:
            return self._fernet.decrypt(ciphertext).decode()
        except InvalidToken as exc:
            # Almost always means ENCRYPTION_KEY was rotated or differs between
            # environments. Fail loudly — silently returning None here would
            # look like "user never connected Gmail".
            raise RuntimeError(
                "Failed to decrypt token — ENCRYPTION_KEY may have changed."
            ) from exc


_cipher: TokenCipher | None = None


def get_cipher() -> TokenCipher:
    global _cipher
    if _cipher is None:
        _cipher = TokenCipher()
    return _cipher
