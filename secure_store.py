import os
import sqlite3
import base64
from typing import Optional
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet

_DB_PATH = os.getenv("USERDATA_DB", "userdata.db")
_MASTER_KEY = os.getenv("MASTER_KEY")


def _get_master_key() -> bytes:
    if not _MASTER_KEY:
        raise RuntimeError("MASTER_KEY environment variable not set")
    return _MASTER_KEY.encode()


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS userdata (user_id TEXT PRIMARY KEY, value BLOB NOT NULL)"
    )
    return conn


def _derive_key(user_id: str) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=user_id.encode(),
        iterations=390000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(_get_master_key()))
    return key


def store_user_data(user_id: str, value: str) -> None:
    """Encrypt and store *value* for *user_id*."""
    f = Fernet(_derive_key(user_id))
    token = f.encrypt(value.encode())
    conn = _get_db()
    with conn:
        conn.execute(
            "REPLACE INTO userdata (user_id, value) VALUES (?, ?)", (user_id, token)
        )
    conn.close()


def retrieve_user_data(user_id: str) -> Optional[str]:
    """Return decrypted value for *user_id* or ``None`` if not found."""
    conn = _get_db()
    row = conn.execute(
        "SELECT value FROM userdata WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    token = row[0]
    f = Fernet(_derive_key(user_id))
    return f.decrypt(token).decode()
