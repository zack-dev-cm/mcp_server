"""Core MCP demo server and tool definitions."""

import os
import datetime as dt
import json
import logging
import random
import socket
import threading
import uuid
import importlib
import pkgutil
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn
import gradio as gr

PROTOCOL_VERSION = "2025-03-26"
SERVER_ID = f"mcp-demo-{uuid.uuid4()}"
START_TIME = dt.datetime.utcnow()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mcp")

iso_now = lambda: dt.datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class JSONRPCError(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Union[str, int, None]
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None


class Resource(BaseModel):
    uri: str
    description: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ToolInput(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True


class Tool(BaseModel):
    id: str
    name: str
    description: str
    inputs: List[ToolInput]
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    handler: Any = None


class Prompt(BaseModel):
    id: str
    name: str
    description: str
    template: str


class Session(BaseModel):
    session_id: str
    created: str
    client_version: str


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------
resources: Dict[str, Resource] = {}
tools: Dict[str, Tool] = {}
prompts: Dict[str, Prompt] = {}
sessions: Dict[str, Session] = {}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def mcp_tool(name: str, description: str, inputs: List[ToolInput]):
    """Decorator to register a function as an MCP tool."""

    def decorator(fn):
        tool_id = str(uuid.uuid4())
        tools[tool_id] = Tool(
            id=tool_id,
            name=name,
            description=description,
            inputs=inputs,
            handler=fn,
        )
        return fn

    return decorator


def find_free_port(start: int = 7860, end: int = 7960) -> int:
    """Return first free port in range."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise OSError(f"No free port in range {start}-{end}")


def load_plugins(path: str = "plugins") -> None:
    """Dynamically import modules from *path* to register tools."""
    full = os.path.join(os.path.dirname(__file__), path)
    if not os.path.isdir(full):
        return
    for _, mod, _ in pkgutil.iter_modules([full]):
        try:
            importlib.import_module(f"{path}.{mod}")
            logger.info("Loaded plugin %s", mod)
        except ModuleNotFoundError as e:
            logger.warning("Skipping plugin %s: %s", mod, e)
        except Exception as e:
            logger.exception("Failed to load plugin %s: %s", mod, e)


# ---------------------------------------------------------------------------
# Mock tools
# ---------------------------------------------------------------------------
@mcp_tool(
    "echo",
    "Echo back text",
    [ToolInput(name="text", type="string", description="Text to echo")],
)
async def echo_tool(p):
    return {"echo": p["text"], "timestamp": iso_now()}


@mcp_tool(
    "calculator",
    "Simple arithmetic eval",
    [ToolInput(name="expression", type="string", description="e.g. '2 + 2'")],
)
async def calculator_tool(p):
    try:
        return {"result": eval(p["expression"], {"__builtins__": {}})}
    except Exception as e:
        raise HTTPException(400, str(e))


@mcp_tool(
    "weather.fake",
    "Random weather",
    [ToolInput(name="location", type="string", description="City/coords")],
)
async def weather_tool(p):
    return {
        "location": p["location"],
        "temperature_c": round(random.uniform(15, 30), 1),
        "condition": random.choice(["sunny", "cloudy", "rainy", "windy"]),
        "observed": iso_now(),
    }


@mcp_tool(
    "file.search",
    "Search resource descriptions",
    [ToolInput(name="query", type="string", description="Keyword")],
)
async def file_search_tool(p):
    term = p["query"].lower()
    hits = [r for r in resources.values() if term in r.description.lower()]
    return {"matches": [r.dict() for r in hits]}


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------
resources["memory://welcome-note"] = Resource(
    uri="memory://welcome-note",
    description="Welcome note explaining how to use the demo MCP server",
    metadata={"author": "system", "created": iso_now()},
)

prompts["hello-world"] = Prompt(
    id="hello-world",
    name="Hello World",
    description="Greets the user",
    template="You are a helpful AI. Greet the user.",
)

# Load optional tool plugins
load_plugins()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="MCP Demo Server", version=PROTOCOL_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.exception_handler(Exception)
async def universal_error(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"error": str(exc)})


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "uptime": str(dt.datetime.utcnow() - START_TIME),
        "now": iso_now(),
    }


@app.get("/v1/resources")
async def list_resources():
    return [r.dict() for r in resources.values()]


@app.get("/v1/tool")
async def list_tools():
    return [{tid: t.dict(exclude={"handler"})} for tid, t in tools.items()]


@app.get("/v1/prompts")
async def list_prompts():
    return [p.dict() for p in prompts.values()]


class InitReq(BaseModel):
    id: Union[str, int]
    jsonrpc: str = "2.0"
    method: str = "initialize"
    params: Dict[str, Any]


@app.post("/v1/initialize")
async def initialize(req: InitReq):
    sess_id = str(uuid.uuid4())
    sessions[sess_id] = Session(
        session_id=sess_id,
        created=iso_now(),
        client_version=req.params.get("version", "unknown"),
    )
    return JSONRPCResponse(
        id=req.id,
        result={
            "serverId": SERVER_ID,
            "protocolVersion": PROTOCOL_VERSION,
            "sessionId": sess_id,
            "serverTime": iso_now(),
        },
    )


class InvokeReq(BaseModel):
    id: Union[str, int]
    jsonrpc: str = "2.0"
    method: str
    params: Dict[str, Any]


@app.post("/v1/tool/{tool_id}/invoke")
async def invoke_tool(tool_id: str, req: InvokeReq):
    if tool_id not in tools:
        raise HTTPException(404, "Tool not found")
    result = await tools[tool_id].handler(req.params)
    return JSONRPCResponse(id=req.id, result=result)


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------
with gr.Blocks(title="MCP Demo UI") as demo:
    gr.Markdown(
        """## MCP Demo – Gradio UI
Use the tabs to explore resources, invoke tools, or chat via the echo tool."""
    )

    with gr.Tabs():
        with gr.TabItem("Resources"):
            df = gr.Dataframe(
                headers=["URI", "Description"], datatype=["str", "str"], interactive=False
            )
            gr.Button("Refresh").click(
                lambda: [[r.uri, r.description] for r in resources.values()], None, df
            )
            df.value = [[r.uri, r.description] for r in resources.values()]

        with gr.TabItem("Tools"):
            dd = gr.Dropdown(choices=[(t.name, tid) for tid, t in tools.items()], label="Tool")
            param = gr.JSON(label="Params (JSON)")
            out = gr.JSON()

            async def run_tool(tid: str, p: Dict[str, Any]) -> Dict[str, Any]:
                return await tools[tid].handler(p)

            gr.Button("Run").click(run_tool, [dd, param], out)

        with gr.TabItem("Chat"):
            chat = gr.Chatbot()
            msg = gr.Textbox()

            async def echo_chat(user: str, hist: Optional[List[List[str]]]) -> Tuple[List[List[str]], str]:
                hist = hist or []
                res = await echo_tool({"text": user})
                return hist + [[user, json.dumps(res, indent=2)]], ""

            gr.Button("Send").click(echo_chat, [msg, chat], [chat, msg])


def run_servers(api_port: int = 8000) -> None:
    """Run FastAPI with the Gradio UI mounted on the same port."""
    port = int(os.getenv("PORT", str(api_port)))
    gr.mount_gradio_app(app, demo, path="/")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_servers()

