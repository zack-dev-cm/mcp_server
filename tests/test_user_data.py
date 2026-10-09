import json
from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient
import pytest

from server import app
from secure_store import load_user_data


client = TestClient(app)


def create_token():
    response = client.post(
        "/v1/initialize",
        json={"id": 1, "jsonrpc": "2.0", "params": {}, "method": "initialize"},
    )
    assert response.status_code == 200
    return response.json()["result"]["sessionId"]


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_requires_auth(method):
    response = client.request(method, "/api/user/data", content="{}")
    assert response.status_code == 401


@pytest.mark.parametrize("payload", [None, False, 0, "", [], {}, [1, None], {"foo": "bar"}])
def test_post_get_delete_cycle(payload):
    token = create_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = client.post("/api/user/data", content=json.dumps(payload), headers=headers)
    assert response.status_code == 200
    response = client.get("/api/user/data", headers=headers)
    assert response.status_code == 200
    actual = response.json()
    assert type(actual) is type(payload) and actual == payload
    other = create_token()
    response = client.get("/api/user/data", headers={"Authorization": f"Bearer {other}"})
    assert response.status_code == 200 and response.json() == {}
    assert client.delete("/api/user/data", headers=headers).status_code == 200
    missing = object()
    assert load_user_data(token, default=missing) is missing
    assert client.get("/api/user/data", headers=headers).json() == {}


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_unconfigured_storage_returns_503_without_writing(isolated_storage, monkeypatch, method):
    token = create_token()
    monkeypatch.delenv("MASTER_KEY")
    response = client.request(method, "/api/user/data", content="{}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert response.json() == {"detail": "User-data storage is not configured"}
    assert not isolated_storage.exists()


def test_nonfinite_json_returns_422_without_writing(isolated_storage):
    token = create_token()
    response = client.post("/api/user/data", content='{"value": NaN}', headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    assert response.status_code == 422
    assert not isolated_storage.exists()


def test_legacy_rows_are_not_overwritten(isolated_storage):
    token = create_token()
    with closing(sqlite3.connect(isolated_storage)) as conn, conn:
        conn.execute("CREATE TABLE userdata (user_id TEXT PRIMARY KEY, value BLOB)")
        conn.execute("INSERT INTO userdata VALUES (?, ?)", (token, b"authored-legacy-row"))
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/user/data", headers=headers).status_code == 409
    assert client.post("/api/user/data", json={"replacement": True}, headers=headers).status_code == 409
    with closing(sqlite3.connect(isolated_storage)) as conn:
        assert conn.execute("SELECT value FROM userdata").fetchone()[0] == b"authored-legacy-row"
    assert client.delete("/api/user/data", headers=headers).status_code == 200
    assert load_user_data(token) is None


def test_wrong_key_returns_sanitized_error(isolated_storage, monkeypatch):
    from cryptography.fernet import Fernet
    token = create_token()
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/user/data", json={"authored": "retained"}, headers=headers).status_code == 200
    monkeypatch.setenv("MASTER_KEY", Fernet.generate_key().decode())
    response = client.get("/api/user/data", headers=headers)
    assert response.status_code == 500
    assert response.json() == {"detail": "Stored user data could not be verified"}
    assert client.post("/api/user/data", json={"replacement": True}, headers=headers).status_code == 500

