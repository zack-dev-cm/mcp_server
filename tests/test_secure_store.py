import os
from contextlib import closing
import sqlite3

from cryptography.fernet import Fernet
import pytest

import secure_store as store


VALUES = [None, False, 0, "", [], {}, [1, False, None], {"unicode": "բարև"}, "wonderland"]


def token(path, user="alice"):
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT value FROM userdata WHERE user_id=?", (user,)).fetchone()[0]


@pytest.mark.parametrize("value", VALUES)
def test_json_round_trip_and_aliases(value):
    store.save_user_data("alice", value)
    actual = store.load_user_data("alice")
    assert type(actual) is type(value) and actual == value


def test_absence_and_stored_null():
    missing = object()
    assert store.load_user_data("absent", default=missing) is missing
    store.store_user_data("alice", None)
    assert store.retrieve_user_data("alice", default=missing) is None
    assert store.retrieve_user_data("absent") is None


def test_ciphertext_is_randomized_and_authenticated(isolated_storage):
    store.store_user_data("alice", "wonderland")
    first = token(isolated_storage)
    store.store_user_data("alice", "wonderland")
    second = token(isolated_storage)
    assert first != second
    assert first.startswith(store.TOKEN_PREFIX) and second.startswith(store.TOKEN_PREFIX)
    assert b"wonderland" not in first
    raw = Fernet(os.environ["MASTER_KEY"].encode()).decrypt(first[len(store.TOKEN_PREFIX):])
    assert b"wonderland" in raw


@pytest.mark.parametrize("key", [None, "", "default_secret", "invalid", "բարև"])
@pytest.mark.parametrize("operation", ["store", "retrieve", "delete"])
def test_missing_or_invalid_key_never_creates_database(isolated_storage, monkeypatch, key, operation):
    if key is None:
        monkeypatch.delenv("MASTER_KEY")
    else:
        monkeypatch.setenv("MASTER_KEY", key)
    with pytest.raises(store.StorageConfigurationError):
        if operation == "store":
            store.store_user_data("alice", "original")
        elif operation == "retrieve":
            store.retrieve_user_data("alice")
        else:
            store.delete_user_data("alice")
    assert not isolated_storage.exists()


def test_wrong_key_cannot_read_or_overwrite(isolated_storage, monkeypatch):
    store.store_user_data("alice", {"original": True})
    before = token(isolated_storage)
    original_key = os.environ["MASTER_KEY"]
    monkeypatch.setenv("MASTER_KEY", Fernet.generate_key().decode())
    with pytest.raises(store.StorageIntegrityError):
        store.load_user_data("alice")
    with pytest.raises(store.StorageIntegrityError):
        store.save_user_data("alice", {"replacement": True})
    assert token(isolated_storage) == before
    monkeypatch.setenv("MASTER_KEY", original_key)
    assert store.load_user_data("alice") == {"original": True}


def test_ciphertext_cannot_move_between_identities(isolated_storage):
    store.save_user_data("alice", {"private": "alice"})
    store.save_user_data("bob", {"private": "bob"})
    with closing(sqlite3.connect(isolated_storage)) as conn, conn:
        conn.execute("UPDATE userdata SET value=? WHERE user_id='bob'", (token(isolated_storage),))
    with pytest.raises(store.StorageIntegrityError):
        store.load_user_data("bob")
    assert store.load_user_data("alice") == {"private": "alice"}


def test_tampering_is_rejected_without_replacement(isolated_storage):
    store.save_user_data("alice", {"original": True})
    original = token(isolated_storage)
    offset = len(store.TOKEN_PREFIX) + 30
    damaged = original[:offset] + (b"A" if original[offset:offset+1] != b"A" else b"B") + original[offset+1:]
    with closing(sqlite3.connect(isolated_storage)) as conn, conn:
        conn.execute("UPDATE userdata SET value=? WHERE user_id='alice'", (damaged,))
    with pytest.raises(store.StorageIntegrityError):
        store.load_user_data("alice")
    with pytest.raises(store.StorageIntegrityError):
        store.save_user_data("alice", {"replacement": True})
    assert token(isolated_storage) == damaged


def test_delete_preserves_other_identity():
    store.save_user_data("alice", None)
    store.save_user_data("bob", False)
    store.delete_user_data("alice")
    missing = object()
    assert store.load_user_data("alice", default=missing) is missing
    assert store.load_user_data("bob") is False


@pytest.mark.parametrize("value", [object(), float("nan"), float("inf")])
def test_invalid_value_does_not_create_database(isolated_storage, value):
    with pytest.raises(store.StorageValueError):
        store.save_user_data("alice", value)
    assert not isolated_storage.exists()


def test_sql_failure_rolls_back_and_connection_closes(isolated_storage):
    store.save_user_data("alice", {"original": True})
    before = token(isolated_storage)
    with closing(sqlite3.connect(isolated_storage)) as conn, conn:
        conn.execute("CREATE TRIGGER reject_write BEFORE INSERT ON userdata WHEN NEW.user_id='alice' BEGIN SELECT RAISE(ABORT, 'authored failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        store.save_user_data("alice", {"replacement": True})
    assert token(isolated_storage) == before
    with closing(sqlite3.connect(isolated_storage, timeout=0.1)) as conn, conn:
        conn.execute("DROP TRIGGER reject_write")
    store.save_user_data("alice", {"retry": True})
    assert store.load_user_data("alice") == {"retry": True}
