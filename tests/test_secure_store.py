import importlib
import sqlite3
import pathlib
import sys


def test_store_and_retrieve(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("USERDATA_DB", str(db_path))
    monkeypatch.setenv("MASTER_KEY", "secret_master")

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    import secure_store
    secure_store = importlib.reload(secure_store)

    secure_store.store_user_data("alice", "wonderland")
    assert secure_store.retrieve_user_data("alice") == "wonderland"

    # raw stored value should not match plaintext
    conn = sqlite3.connect(db_path)
    token = conn.execute("SELECT value FROM userdata WHERE user_id=?", ("alice",)).fetchone()[0]
    conn.close()
    assert b"wonderland" not in token
