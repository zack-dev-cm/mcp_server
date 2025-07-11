import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from plugins.audio_transcriber import _download_audio


class DummyClient:
    def __init__(self, resp: httpx.Response):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url):
        return self._resp


@pytest.mark.asyncio
async def test_download_audio_uses_content_type(tmp_path, monkeypatch):
    content = b"abc123"
    req = httpx.Request("GET", "https://api.elevenlabs.io/speech")
    resp = httpx.Response(
        200, request=req, content=content, headers={"content-type": "audio/mpeg"}
    )
    dummy = DummyClient(resp)
    monkeypatch.setattr(httpx, "AsyncClient", lambda: dummy)

    path = await _download_audio("https://api.elevenlabs.io/speech")
    assert path.endswith(".mp3")
    with open(path, "rb") as f:
        assert f.read() == content
    os.remove(path)
