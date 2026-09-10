import base64
import hashlib
import logging
import os
import secrets
import stat

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import settings

logger = logging.getLogger("healthchecker.security")

_fernet: Fernet | None = None


def _load_or_create_key() -> bytes:
    """Resolve the Fernet key used to encrypt API keys at rest.

    Priority: HC_APP_SECRET_KEY env var (recommended for production) falls
    back to a key file persisted in the data volume, generated on first run.
    """
    if settings.app_secret_key:
        raw = settings.app_secret_key.strip()
        try:
            decoded = base64.urlsafe_b64decode(raw)
            if len(decoded) == 32:
                return raw.encode()
        except Exception:
            pass
        # Not already a valid 32-byte Fernet key; derive one deterministically
        # so any passphrase-like string works.
        digest = hashlib.sha256(raw.encode()).digest()
        return base64.urlsafe_b64encode(digest)

    key_path = settings.secret_key_path
    if key_path.exists():
        return key_path.read_bytes().strip()

    key = Fernet.generate_key()
    key_path.write_bytes(key)
    try:
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, NotImplementedError):
        pass
    logger.warning(
        "Generated a new encryption key at %s. Back this file up, or set "
        "HC_APP_SECRET_KEY to a fixed value, or stored API keys become unrecoverable.",
        key_path,
    )
    return key


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def encrypt_secret(plaintext: str | None) -> str | None:
    if not plaintext:
        return None
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str | None) -> str | None:
    if not ciphertext:
        return None
    try:
        return get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Failed to decrypt stored secret; encryption key may have changed.")
        return None


def mask_secret(plaintext_len_hint: str | None) -> str | None:
    if not plaintext_len_hint:
        return None
    return "*" * 8


_basic = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(_basic)):
    """Optional HTTP Basic auth gate for the whole app.

    No-op unless HC_AUTH_USERNAME / HC_AUTH_PASSWORD are both set.
    """
    if not settings.auth_username or not settings.auth_password:
        return True

    valid_user = credentials is not None and secrets.compare_digest(
        credentials.username, settings.auth_username
    )
    valid_pass = credentials is not None and secrets.compare_digest(
        credentials.password, settings.auth_password
    )
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True
