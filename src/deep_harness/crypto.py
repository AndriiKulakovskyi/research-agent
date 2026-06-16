"""Encryption for secrets stored at rest (currently users' Modal API tokens).

The Modal token secret is the one credential the app persists on a user's
behalf. It is encrypted with Fernet (AES-128-CBC + HMAC) before it touches the
database, so DB dumps, backups, logs, and accidental commits never contain
plaintext credentials.

Key resolution, in order:
  1. ``DEEP_HARNESS_SECRET_KEY`` env var — use this in production. Any string; a
     Fernet key is derived from its SHA-256. Source it from a secrets manager.
  2. A per-deployment key file under the workspace (``.secret_key``), generated
     once with 0600 perms if absent. Convenient for local/dev use, but it lives
     on the same disk as the data — set the env var for real deployments.

Legacy plaintext values (written before encryption existed) are detected on read
and returned unchanged, so existing databases keep working and re-encrypt on the
next write.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import stat

from cryptography.fernet import Fernet, InvalidToken

from deep_harness.config import get_settings

logger = logging.getLogger(__name__)

ENV_KEY = "DEEP_HARNESS_SECRET_KEY"
_KEY_FILENAME = ".secret_key"
_PREFIX = "enc:"

# Cache the cipher, keyed by its source so it self-invalidates when the workspace
# (and thus the fallback key file) changes — mirrors the engine/graph caches and
# keeps tests, which swap workspaces between cases, correct without extra hooks.
_cache: tuple[str, Fernet] | None = None


def _derive_fernet_key(material: bytes) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(material).digest())


def _load_key() -> bytes:
    env = os.environ.get(ENV_KEY)
    if env:
        return _derive_fernet_key(env.encode())
    key_path = get_settings().workspace_dir / _KEY_FILENAME
    if key_path.exists():
        return key_path.read_bytes().strip()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    try:
        key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
    logger.warning(
        "%s is not set; generated a key file at %s. This is fine for local/dev "
        "use, but for production (especially multi-tenant) set %s from a secrets "
        "manager — the key file sits on the same disk as the data it protects.",
        ENV_KEY,
        key_path,
        ENV_KEY,
    )
    return key


def _cipher() -> Fernet:
    global _cache
    env = os.environ.get(ENV_KEY, "")
    source = f"env:{env}" if env else f"file:{get_settings().workspace_dir}"
    if _cache is None or _cache[0] != source:
        _cache = (source, Fernet(_load_key()))
    return _cache[1]


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage. Empty input stays empty (means 'no secret')."""
    if not plaintext:
        return ""
    return _PREFIX + _cipher().encrypt(plaintext.encode()).decode()


def decrypt_secret(value: str) -> str:
    """Decrypt a stored secret. Values without the encryption prefix are treated
    as legacy plaintext and returned unchanged (seamless migration). A value that
    cannot be decrypted (e.g. the key was rotated) is treated as absent rather
    than raising, so a lost key degrades to 'no secret' instead of a crash."""
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value  # legacy plaintext
    try:
        return _cipher().decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken:
        logger.warning(
            "Could not decrypt a stored secret (wrong/rotated %s, or tampering); "
            "treating it as absent.",
            ENV_KEY,
        )
        return ""
