import base64
import hashlib
import json
import os
import sqlite3
from typing import Any, Optional

from cryptography.fernet import Fernet

DATA_DIR = os.path.join(os.path.dirname(__file__), "user_store")
os.makedirs(DATA_DIR, exist_ok=True)


def _path(user_id: str) -> str:
    return os.path.join(DATA_DIR, f"{user_id}.json")


def load_user_data(user_id: str) -> Optional[Any]:
    """Return stored data for *user_id* or ``None`` if not found."""
    path = _path(user_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_user_data(user_id: str, data: Any) -> None:
    """Persist ``data`` for *user_id*."""
    with open(_path(user_id), "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def store_user_data(user_id: str, data: Any) -> None:
    """Persist encrypted ``data`` for *user_id* using SQLite."""
    db = os.getenv("USERDATA_DB", os.path.join(os.path.dirname(__file__), "user_data.db"))
    key = os.getenv("MASTER_KEY", "default").encode()
    fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(key).digest()))
    enc = fernet.encrypt(data.encode() if isinstance(data, str) else json.dumps(data).encode())
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS userdata (user_id TEXT PRIMARY KEY, value BLOB)"
    )
    conn.execute(
        "REPLACE INTO userdata (user_id, value) VALUES (?, ?)",
        (user_id, enc),
    )
    conn.commit()
    conn.close()


def delete_user_data(user_id: str) -> None:
    """Delete stored data for *user_id*."""
    try:
        os.remove(_path(user_id))
    except FileNotFoundError:
        pass


def retrieve_user_data(user_id: str) -> Optional[Any]:
    """Return decrypted data for *user_id* stored via :func:`store_user_data`."""
    db = os.getenv("USERDATA_DB", os.path.join(os.path.dirname(__file__), "user_data.db"))
    if not os.path.exists(db):
        return None
    key = os.getenv("MASTER_KEY", "default").encode()
    fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(key).digest()))
    conn = sqlite3.connect(db)
    row = conn.execute("SELECT value FROM userdata WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    if not row:
        return None
    val = fernet.decrypt(row[0])
    try:
        return json.loads(val)
    except Exception:
        return val.decode()
