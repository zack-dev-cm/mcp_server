import os
from pathlib import Path
import tempfile
import httpx
from fastapi import HTTPException
try:
    import openai
except Exception:  # pragma: no cover - optional dependency
    openai = None

from server import mcp_tool, ToolInput

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY and openai else None


async def _download_audio(url: str) -> str:
    """Download audio from *url* to a temporary file and return the path."""
    async with httpx.AsyncClient() as hc:
        resp = await hc.get(url)
        resp.raise_for_status()
        suffix = Path(url).suffix or ".tmp"
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
