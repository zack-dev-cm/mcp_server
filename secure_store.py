"""Authenticated JSON storage with an explicit migration for legacy rows."""

import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


DATA_DIR = os.path.join(os.path.dirname(__file__), "user_store")
TOKEN_PREFIX = b"fernet-v1:"


class StorageConfigurationError(RuntimeError):
    """Protected storage has no valid encryption key."""


class StorageIntegrityError(ValueError):
    """Stored data could not be authenticated for its identity."""


class LegacyDataError(StorageIntegrityError):
    """An old row requires an explicit migration."""


class StorageValueError(ValueError):
    """The input is not a finite JSON value."""


def _get_db_path() -> str:
    return os.getenv("USERDATA_DB", os.path.join(DATA_DIR, "data.db"))


def _cipher() -> Fernet:
    key = os.getenv("MASTER_KEY")
    if not key:
        raise StorageConfigurationError("MASTER_KEY must be a generated Fernet key")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeError):
        raise StorageConfigurationError(
            "MASTER_KEY must be a generated Fernet key"
        ) from None


def _get_db_conn() -> sqlite3.Connection:
    path = _get_db_path()
    Path(path).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path and path != ":memory:":
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS userdata (user_id TEXT PRIMARY KEY, value BLOB)"
        )
    except BaseException:
        conn.close()
        raise
    return conn


def _reject_constant(value: str) -> None:
    raise ValueError("Nonfinite JSON is not supported")


def _encode(user_id: str, data: Any, cipher: Fernet) -> bytes:
    if not isinstance(user_id, str):
        raise StorageValueError("User identity must be a string")
    try:
        text = json.dumps(
            {"user_id": user_id, "data": data}, ensure_ascii=False, allow_nan=False
        )
    except (TypeError, ValueError):
        raise StorageValueError("Data must be a finite JSON value") from None
    return TOKEN_PREFIX + cipher.encrypt(text.encode("utf-8"))


def _decode(user_id: str, token: bytes, cipher: Fernet) -> Any:
    if not isinstance(token, bytes):
        raise StorageIntegrityError("Stored data cannot be authenticated")
    if not token.startswith(TOKEN_PREFIX):
        raise LegacyDataError("Stored data require an explicit legacy migration")
    try:
        payload = json.loads(
            cipher.decrypt(token[len(TOKEN_PREFIX):]), parse_constant=_reject_constant
        )
        if (
            not isinstance(payload, dict)
            or set(payload) != {"user_id", "data"}
            or payload["user_id"] != user_id
        ):
            raise ValueError("Identity mismatch")
        return payload["data"]
    except (InvalidToken, ValueError, TypeError, UnicodeError, KeyError):
        raise StorageIntegrityError("Stored data cannot be authenticated") from None


def store_user_data(user_id: str, data: Any) -> None:
    """Store JSON data, without silently replacing legacy or unverifiable rows."""
    cipher = _cipher()
    encoded = _encode(user_id, data, cipher)
    with closing(_get_db_conn()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT value FROM userdata WHERE user_id=?", (user_id,)
        ).fetchone()
        if existing is not None:
            _decode(user_id, existing[0], cipher)
        conn.execute(
            "REPLACE INTO userdata (user_id, value) VALUES (?, ?)",
            (user_id, encoded),
        )


def retrieve_user_data(user_id: str, *, default: Any = None) -> Any:
    """Return JSON data, including null, or *default* when the row is absent."""
    cipher = _cipher()
    with closing(_get_db_conn()) as conn:
        row = conn.execute(
            "SELECT value FROM userdata WHERE user_id=?", (user_id,)
        ).fetchone()
    return default if row is None else _decode(user_id, row[0], cipher)


def load_user_data(user_id: str, *, default: Any = None) -> Any:
    """Compatibility alias; the default remains None for an absent row."""
    return retrieve_user_data(user_id, default=default)


def save_user_data(user_id: str, data: Any) -> None:
    store_user_data(user_id, data)


def delete_user_data(user_id: str) -> None:
    """Delete only this identity's SQL row, including a legacy row."""
    _cipher()
    with closing(_get_db_conn()) as conn, conn:
        conn.execute("DELETE FROM userdata WHERE user_id=?", (user_id,))


def _decode_legacy(token: bytes, legacy_key: str) -> Any:
    """Decode the unauthenticated old format only during an explicit migration."""
    try:
        raw = base64.b64decode(token, validate=True)
        key = hashlib.sha256(legacy_key.encode("utf-8")).digest()
        plain = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
        return json.loads(plain.decode("utf-8"), parse_constant=_reject_constant)
    except (ValueError, TypeError, UnicodeError):
        raise StorageIntegrityError("Legacy data could not be decoded as finite JSON") from None


def _backup_database(source: Path, destination: Path) -> None:
    """Create a private, non-overwriting SQLite backup before any row update."""
    if source.resolve() == destination.resolve():
        raise ValueError("Backup must be separate from the source database")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        # A second read connection copies the committed snapshot while the
        # migration holds the writer reservation, before any row is updated.
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(destination)) as dst:
                src.backup(dst)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def migrate_legacy_user_data(
    legacy_key: str, *, dry_run: bool = True, backup_path: str | Path | None = None
) -> dict:
    """Validate all rows, then optionally migrate in one backed-up transaction.

    The old format has no authentication. Decoding JSON cannot prove that old
    contents were untampered; operators must verify their known source data.
    """
    cipher = _cipher()
    if not isinstance(legacy_key, str):
        raise ValueError("The legacy key must be explicitly supplied")
    source = Path(_get_db_path()).resolve()
    with closing(sqlite3.connect(source.as_uri() + "?mode=rw", uri=True)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT user_id, value FROM userdata ORDER BY user_id").fetchall()
        updates = []
        current = 0
        for user_id, token in rows:
            if isinstance(token, bytes) and token.startswith(TOKEN_PREFIX):
                _decode(user_id, token, cipher)
                current += 1
            else:
                data = _decode_legacy(token, legacy_key)
                updates.append((_encode(user_id, data, cipher), user_id))
        backup = None
        if not dry_run and updates:
            if backup_path is None:
                raise ValueError("Applying a migration requires a new backup path")
            backup = Path(backup_path).resolve()
            _backup_database(source, backup)
            conn.executemany("UPDATE userdata SET value=? WHERE user_id=?", updates)
        else:
            conn.rollback()
        return {
            "rows": len(rows),
            "legacy_rows": len(updates),
            "already_current": current,
            "updated_rows": len(updates) if not dry_run else 0,
            "applied": not dry_run,
            "backup": str(backup) if backup is not None else None,
        }
