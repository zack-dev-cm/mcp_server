import os
import tempfile
from pathlib import Path

import httpx
from fastapi import HTTPException

try:
    import openai
except Exception:  # pragma: no cover - optional dependency
    openai = None

from server import ToolInput, mcp_tool


def _guess_extension(content_type: str) -> str:
    """Return file extension for HTTP *content_type*."""
    ct = content_type.split(";", 1)[0].lower()
    mapping = {
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/x-mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/webm": ".webm",
        "audio/mp4": ".mp4",
        "video/mp4": ".mp4",
        "audio/x-m4a": ".m4a",
    }
    return mapping.get(ct, "")


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and openai else None


async def _download_audio(url: str) -> str:
    """Download audio from *url* to a temporary file and return the path."""
    async with httpx.AsyncClient() as hc:
        resp = await hc.get(url)
        resp.raise_for_status()
        cleaned_url = url.split("?", 1)[0]
        suffix = Path(cleaned_url).suffix
        if not suffix:
            suffix = _guess_extension(resp.headers.get("content-type", ""))
        if not suffix:
            suffix = ".tmp"
        fd, path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        with open(path, "wb") as f:
            f.write(resp.content)
    return path


@mcp_tool(
    "audio.transcribe",
    "Transcribe audio using OpenAI Whisper",
    [ToolInput(name="url", type="string", description="Public URL to audio file")],
)
async def transcribe_tool(params):
    if not client:
        raise HTTPException(500, "OPENAI_API_KEY not configured")
    url = params["url"]
    cleaned_path = await _download_audio(url)
    try:
        with open(cleaned_path, "rb") as f:
            resp = await client.audio.transcriptions.create(model="whisper-1", file=f)
    finally:
        os.remove(cleaned_path)
    return {"text": resp.text}
