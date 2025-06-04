import os
from fastapi import HTTPException
import openai
from server import mcp_tool, ToolInput

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

@mcp_tool(
    "openai.vision",
    "Image understanding via OpenAI's vision models",
    [
        ToolInput(name="image_url", type="string", description="Public image URL"),
        ToolInput(name="prompt", type="string", description="Optional prompt", required=False),
        ToolInput(name="model", type="string", description="OpenAI model", required=False),
    ],
)
async def openai_vision_tool(params):
    if not OPENAI_API_KEY:
        raise HTTPException(500, "OPENAI_API_KEY not configured")
    model = params.get("model", "gpt-4-turbo")
    user_prompt = params.get("prompt", "Describe the image.")
    resp = await openai.ChatCompletion.acreate(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt},
                {"type": "image_url", "image_url": {"url": params["image_url"]}},
            ],
        }],
    )
    return {"reply": resp.choices[0].message.content}

