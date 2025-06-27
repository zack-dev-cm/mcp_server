import os
import sqlite3
import base64
import hashlib
from typing import Any, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "user_store")
os.makedirs(DATA_DIR, exist_ok=True)


def _get_db_path() -> str:
    return os.getenv("USERDATA_DB", os.path.join(DATA_DIR, "data.db"))


def _get_db_conn() -> sqlite3.Connection:
    path = _get_db_path()
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS userdata (user_id TEXT PRIMARY KEY, value BLOB)"
    )
    return conn


def _master_key() -> bytes:
    key = os.getenv("MASTER_KEY", "default_secret").encode("utf-8")
    return hashlib.sha256(key).digest()


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _encrypt(text: str) -> bytes:
    return base64.b64encode(_xor(text.encode("utf-8"), _master_key()))


def _decrypt(token: bytes) -> str:
    return _xor(base64.b64decode(token), _master_key()).decode("utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def store_user_data(user_id: str, data: Any) -> None:
    """Store ``data`` for *user_id* in the database."""
    conn = _get_db_conn()
    import json
    enc = _encrypt(json.dumps(data))
    conn.execute(
        "REPLACE INTO userdata (user_id, value) VALUES (?, ?)",
        (user_id, enc),
    )
    conn.commit()
    conn.close()


def retrieve_user_data(user_id: str) -> Optional[str]:
    """Return stored data for *user_id* or ``None`` if not found."""
    conn = _get_db_conn()
    row = conn.execute(
        "SELECT value FROM userdata WHERE user_id=?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    import json
    return json.loads(_decrypt(row[0]))


# Backwards compat for earlier file-based API ---------------------------------

def load_user_data(user_id: str) -> Optional[str]:
    return retrieve_user_data(user_id)


def save_user_data(user_id: str, data: Any) -> None:
    store_user_data(user_id, data)


def delete_user_data(user_id: str) -> None:
    conn = _get_db_conn()
    conn.execute("DELETE FROM userdata WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
