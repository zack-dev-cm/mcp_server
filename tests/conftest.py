"""Local fixtures keep repository tests away from user data and providers."""

import os
from pathlib import Path
import socket
import sys

from cryptography.fernet import Fernet
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["ELEVENLABS_MCP_SECRET"] = "local-test-secret"
os.environ.pop("OPENAI_API_KEY", None)


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    path = tmp_path / "data.db"
    monkeypatch.setenv("USERDATA_DB", str(path))
    monkeypatch.setenv("MASTER_KEY", Fernet.generate_key().decode("ascii"))
    connect = socket.socket.connect

    def offline(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("Repository tests must not contact external services")
        return connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", offline)
    return path
