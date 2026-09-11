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

logger = logging.getLogger("checkarr.security")

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


def resolve_secret(env_var: str | None, encrypted: str | None) -> str | None:
    """Every secret field (Service.api_key, Service.jellyfin_admin_password,
    NotificationChannel.secret) can be sourced from an environment variable
    instead of the encrypted database column - see apply_secret_field below,
    which enforces that at most one of the two is ever populated at a time.
    Reads the env var fresh on every call (not cached) since it's cheap and
    keeps this in sync with whatever the container's actually been given."""
    if env_var:
        value = os.environ.get(env_var)
        if not value:
            logger.warning(
                "Environment variable %r (configured as a secret source) is not set - "
                "treating the secret as unconfigured",
                env_var,
            )
        return value or None
    return decrypt_secret(encrypted)


def apply_secret_field(
    obj,
    encrypted_attr: str,
    env_var_attr: str,
    *,
    use_env: bool | None,
    env_var: str | None,
    literal_value: str | None,
    clear: bool = False,
) -> None:
    """Applies one secret field's "use environment variable" toggle in
    place, on either a Service or a NotificationChannel (encrypted_attr/
    env_var_attr name whichever pair of columns apply).

    - use_env=True switches to env-var mode: env_var is required, and any
      stored encrypted secret is cleared - the point of this mode is that
      the secret no longer lives in the database/on disk at all.
    - use_env=False switches to (or stays in) literal mode: the env var
      name is cleared, and if a literal_value was actually given, it
      replaces the stored secret (a blank value keeps whatever's already
      stored, same "leave blank to keep existing" convention this had
      before env-var mode existed).
    - use_env=None means this request didn't address the mode at all -
      only applies a literal_value if one was given (and, in that case,
      also switches off env-var mode, since providing a literal value is
      an unambiguous signal). Keeps older/direct API callers that only
      ever send the literal secret field working unchanged.
    - clear=True (either mode) unsets the secret entirely rather than
      leaving the existing one in place.
    """
    if use_env is True:
        if not env_var or not env_var.strip():
            raise HTTPException(400, "Environment variable name is required")
        setattr(obj, encrypted_attr, None)
        setattr(obj, env_var_attr, env_var.strip())
        return
    if use_env is False:
        setattr(obj, env_var_attr, None)
    if clear:
        setattr(obj, encrypted_attr, None)
    elif literal_value:
        setattr(obj, encrypted_attr, encrypt_secret(literal_value))
        if use_env is None:
            setattr(obj, env_var_attr, None)


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
