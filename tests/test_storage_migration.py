import base64
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from cryptography.fernet import Fernet
import pytest

import secure_store as store


LEGACY_KEY = "authored-legacy-key"


def legacy_token(value, key=LEGACY_KEY):
    raw = json.dumps(value).encode("utf-8")
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return base64.b64encode(bytes(b ^ digest[i % len(digest)] for i, b in enumerate(raw)))


def add_legacy(path, values):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE IF NOT EXISTS userdata (user_id TEXT PRIMARY KEY, value BLOB)")
        conn.executemany("INSERT INTO userdata VALUES (?, ?)", [(user, legacy_token(value)) for user, value in values.items()])


def rows(path):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT user_id, value FROM userdata ORDER BY user_id").fetchall()


def test_legacy_requires_explicit_migration(isolated_storage):
    add_legacy(isolated_storage, {"alice": {"original": True}})
    before = rows(isolated_storage)
    with pytest.raises(store.LegacyDataError):
        store.load_user_data("alice")
    with pytest.raises(store.LegacyDataError):
        store.save_user_data("alice", {"replacement": True})
    assert rows(isolated_storage) == before


def test_dry_run_preserves_all_rows(isolated_storage, tmp_path):
    add_legacy(isolated_storage, {"alice": False, "bob": None})
    before = rows(isolated_storage)
    backup = tmp_path / "unused.db"
    result = store.migrate_legacy_user_data(LEGACY_KEY, backup_path=backup)
    assert result["legacy_rows"] == 2
    assert result["updated_rows"] == 0
    assert result["applied"] is False
    assert rows(isolated_storage) == before
    assert not backup.exists()


def test_mixed_migration_backup_and_repeat(isolated_storage, tmp_path):
    values = {"alice": [], "bob": None, "carol": {"unicode": "բարև"}}
    add_legacy(isolated_storage, values)
    store.save_user_data("current", 0)
    before = rows(isolated_storage)
    backup = tmp_path / "before.db"
    result = store.migrate_legacy_user_data(LEGACY_KEY, dry_run=False, backup_path=backup)
    assert result["updated_rows"] == 3
    assert result["already_current"] == 1
    assert rows(backup) == before
    assert backup.stat().st_mode & 0o777 == 0o600
    for user, expected in values.items():
        actual = store.load_user_data(user)
        assert type(actual) is type(expected) and actual == expected
    assert store.load_user_data("current") == 0
    after = rows(isolated_storage)
    repeated = store.migrate_legacy_user_data(LEGACY_KEY, dry_run=False, backup_path=backup)
    assert repeated["updated_rows"] == 0
    assert rows(isolated_storage) == after
    assert rows(backup) == before


@pytest.mark.parametrize("wrong", ["legacy", "current"])
def test_wrong_key_preserves_source(isolated_storage, tmp_path, monkeypatch, wrong):
    add_legacy(isolated_storage, {"alice": {"original": True}})
    store.save_user_data("current", "retained")
    before = rows(isolated_storage)
    key = LEGACY_KEY
    if wrong == "legacy":
        key = "incorrect-legacy-key"
    else:
        monkeypatch.setenv("MASTER_KEY", Fernet.generate_key().decode("ascii"))
    backup = tmp_path / "unused.db"
    with pytest.raises(store.StorageIntegrityError):
        store.migrate_legacy_user_data(key, dry_run=False, backup_path=backup)
    assert rows(isolated_storage) == before
    assert not backup.exists()


def test_failed_update_rolls_back_and_retains_backup(isolated_storage, tmp_path):
    add_legacy(isolated_storage, {"alice": "first", "bob": "second"})
    with closing(sqlite3.connect(isolated_storage)) as conn, conn:
        conn.execute("CREATE TRIGGER stop_update BEFORE UPDATE ON userdata WHEN NEW.user_id='bob' BEGIN SELECT RAISE(ABORT, 'authored failure'); END")
    before = rows(isolated_storage)
    backup = tmp_path / "before.db"
    with pytest.raises(sqlite3.IntegrityError):
        store.migrate_legacy_user_data(LEGACY_KEY, dry_run=False, backup_path=backup)
    assert rows(isolated_storage) == before
    assert rows(backup) == before
    with closing(sqlite3.connect(isolated_storage)) as conn, conn:
        conn.execute("DROP TRIGGER stop_update")
    assert store.migrate_legacy_user_data(LEGACY_KEY, dry_run=False, backup_path=tmp_path / "retry.db")["updated_rows"] == 2


def test_interrupted_update_rolls_back(isolated_storage, tmp_path, monkeypatch):
    add_legacy(isolated_storage, {"alice": "first", "bob": "second"})
    before = rows(isolated_storage)
    connect = sqlite3.connect

    class InterruptedConnection(sqlite3.Connection):
        def executemany(self, sql, parameters):
            if sql.startswith("UPDATE userdata"):
                self.execute(sql, next(iter(parameters)))
                raise KeyboardInterrupt
            return super().executemany(sql, parameters)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", lambda *args, **kwargs: connect(*args, factory=InterruptedConnection, **kwargs))
        with pytest.raises(KeyboardInterrupt):
            store.migrate_legacy_user_data(LEGACY_KEY, dry_run=False, backup_path=tmp_path / "before.db")
    assert rows(isolated_storage) == before
    assert rows(tmp_path / "before.db") == before


@pytest.mark.parametrize("destination", ["source", "existing", "missing"])
def test_backup_requirements_preserve_data(isolated_storage, tmp_path, destination):
    add_legacy(isolated_storage, {"alice": "original"})
    before = rows(isolated_storage)
    backup = isolated_storage if destination == "source" else tmp_path / "occupied.db"
    if destination == "existing":
        backup.write_bytes(b"authored existing backup")
    if destination == "missing":
        backup = None
    with pytest.raises((ValueError, FileExistsError)):
        store.migrate_legacy_user_data(LEGACY_KEY, dry_run=False, backup_path=backup)
    assert rows(isolated_storage) == before
    if destination == "existing":
        assert backup.read_bytes() == b"authored existing backup"


def test_missing_source_is_not_created(isolated_storage):
    with pytest.raises(sqlite3.OperationalError):
        store.migrate_legacy_user_data(LEGACY_KEY)
    assert not isolated_storage.exists()


def test_corrupt_legacy_preserves_all_rows(isolated_storage, tmp_path):
    add_legacy(isolated_storage, {"alice": "original"})
    with closing(sqlite3.connect(isolated_storage)) as conn, conn:
        conn.execute("INSERT INTO userdata VALUES ('bob', ?)", (b"invalid!",))
    before = rows(isolated_storage)
    with pytest.raises(store.StorageIntegrityError):
        store.migrate_legacy_user_data(LEGACY_KEY, dry_run=False, backup_path=tmp_path / "unused.db")
    assert rows(isolated_storage) == before


def test_cli_dry_run_apply_and_failure(isolated_storage, tmp_path):
    add_legacy(isolated_storage, {"alice": {"original": True}})
    before = rows(isolated_storage)
    env = os.environ.copy()
    env["LEGACY_MASTER_KEY"] = LEGACY_KEY
    command = [sys.executable, str(Path(store.__file__).with_name("migrate_user_data.py"))]
    dry = subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)
    assert dry.returncode == 0 and json.loads(dry.stdout)["updated_rows"] == 0
    assert rows(isolated_storage) == before
    missing_backup = subprocess.run(command + ["--apply"], env=env, capture_output=True, text=True, timeout=10)
    assert missing_backup.returncode != 0 and rows(isolated_storage) == before
    applied = subprocess.run(command + ["--apply", "--backup", str(tmp_path / "before.db")], env=env, capture_output=True, text=True, timeout=10)
    assert applied.returncode == 0 and json.loads(applied.stdout)["updated_rows"] == 1
    assert store.load_user_data("alice") == {"original": True}
