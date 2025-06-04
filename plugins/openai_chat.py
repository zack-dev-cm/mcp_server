import os
from fastapi import HTTPException
import openai
from server import mcp_tool, ToolInput

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

@mcp_tool(
    "openai.chat",
    "Chat completion via OpenAI API",
    [
        ToolInput(name="prompt", type="string", description="User prompt"),
        ToolInput(name="model", type="string", description="OpenAI model", required=False),
    ],
)
async def openai_chat_tool(params):
    if not OPENAI_API_KEY:
        raise HTTPException(500, "OPENAI_API_KEY not configured")
    model = params.get("model", "gpt-3.5-turbo")
    resp = await openai.ChatCompletion.acreate(
        model=model,
        messages=[{"role": "user", "content": params["prompt"]}],
    )
    return {"reply": resp.choices[0].message.content}

