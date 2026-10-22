"""Secrets that live inside a check's own config rather than on its
service - only the FTP check's password so far. Every other secret has its
own encrypted column (Service.api_key_encrypted and friends); this keeps
these in line with them: encrypted at rest with the same key
(security.encrypt_secret), never sent back out by the API, and "leave it
blank to keep the one already saved" when a check is edited - the same
convention the service form's API key field uses.

Stored as "enc:<fernet token>" so a value saved before this existed (plain
text) can still be told apart and encrypted on startup - see
database._encrypt_check_config_secrets.
"""

from .security import decrypt_secret, encrypt_secret

SECRET_CONFIG_FIELDS: dict[str, tuple[str, ...]] = {"ftp_path": ("password",)}

_PREFIX = "enc:"


def _is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def store_check_config(check_type: str, incoming: dict | None, existing: dict | None = None) -> dict:
    """The config to save for a create/update: secret fields encrypted, a
    blank one keeping whatever was stored before, and the `<key>_set` flags
    mask_check_config adds for the UI dropped again."""
    config = dict(incoming or {})
    for key in SECRET_CONFIG_FIELDS.get(check_type, ()):
        config.pop(f"{key}_set", None)
        value = config.get(key)
        if value:
            config[key] = value if _is_encrypted(value) else _PREFIX + encrypt_secret(str(value))
        elif existing and existing.get(key):
            config[key] = existing[key]
        else:
            config.pop(key, None)
    return config


def mask_check_config(check_type: str, config: dict | None) -> dict:
    """What the API returns: each secret blanked, plus `<key>_set` saying
    whether one is stored, so the form can say "leave blank to keep"."""
    config = dict(config or {})
    for key in SECRET_CONFIG_FIELDS.get(check_type, ()):
        config[f"{key}_set"] = bool(config.get(key))
        config[key] = ""
    return config


def reveal_check_config(check_type: str, config: dict | None) -> dict:
    """The config a check actually runs with - secrets decrypted. A value
    that's still plain text (saved before encryption existed, before the
    startup migration got to it) is passed through as-is."""
    config = dict(config or {})
    for key in SECRET_CONFIG_FIELDS.get(check_type, ()):
        value = config.get(key)
        if _is_encrypted(value):
            config[key] = decrypt_secret(value[len(_PREFIX):]) or ""
    return config
