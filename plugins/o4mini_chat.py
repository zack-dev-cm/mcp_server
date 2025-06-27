import os
from fastapi import HTTPException
import httpx
from server import mcp_tool, ToolInput

O4MINI_ENDPOINT = os.getenv("O4MINI_ENDPOINT", "http://localhost:4900/generate")

@mcp_tool(
    "o4mini.chat",
    "Chat completion using the o4-mini model",
    [ToolInput(name="prompt", type="string", description="User prompt")],
)
async def o4mini_chat_tool(params):
    async with httpx.AsyncClient() as client:
        resp = await client.post(O4MINI_ENDPOINT, json={"prompt": params["prompt"]})
    if resp.status_code != 200:
        raise HTTPException(500, f"Model error: {resp.text}")
    data = resp.json()
    return {"reply": data.get("response", "")}
