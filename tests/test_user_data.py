import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from fastapi.testclient import TestClient

from server import app
from secure_store import load_user_data, DATA_DIR

client = TestClient(app)


def create_token():
    resp = client.post(
        "/v1/initialize",
        json={"id": 1, "jsonrpc": "2.0", "params": {}, "method": "initialize"},
    )
    return resp.json()["result"]["sessionId"]


def test_requires_auth():
    r = client.get("/api/user/data")
    assert r.status_code == 401


def setup_module(module):
    if os.path.isdir(DATA_DIR):
        shutil.rmtree(DATA_DIR)
    os.makedirs(DATA_DIR, exist_ok=True)


def test_post_get_delete_cycle():
    token = create_token()
    payload = {"foo": "bar"}
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post("/api/user/data", json=payload, headers=headers)
    assert r.status_code == 200

    r = client.get("/api/user/data", headers=headers)
    assert r.json() == payload

    # other session should not see data
    other_token = create_token()
    r = client.get("/api/user/data", headers={"Authorization": f"Bearer {other_token}"})
    assert r.json() == {}

    r = client.delete("/api/user/data", headers=headers)
    assert r.status_code == 200
    assert load_user_data(token) is None

