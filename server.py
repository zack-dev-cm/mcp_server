"""Core MCP demo server and tool definitions."""

import os
import datetime as dt
import logging
import random
import socket
import uuid
import importlib
import pkgutil
from typing import Any, Dict, List, Optional, Union
import json
import asyncio
import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from settings import settings
import uvicorn
from secure_store import delete_user_data, load_user_data, save_user_data
try:
    import openai
except Exception:  # pragma: no cover - optional dependency
    openai = None
try:  # optional html sanitizing
    import bleach  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    bleach = None
try:  # optional html->md
    import html2text  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    html2text = None
try:
    from sse_starlette.sse import EventSourceResponse  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    EventSourceResponse = None

PROTOCOL_VERSION = "2025-03-26"
SERVER_ID = f"mcp-demo-{uuid.uuid4()}"
START_TIME = dt.datetime.utcnow()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mcp")


def iso_now() -> str:
    """Return current UTC time in ISO format."""
    return dt.datetime.utcnow().isoformat() + "Z"


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

def get_token(request: Request) -> str:
    """Return bearer token from Authorization header if valid."""
    auth = request.headers.get("authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.split(" ", 1)[1]
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Invalid token")
    return token

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


def _sanitize_html(html: str) -> str:
    """Return sanitized HTML using bleach if available."""
    if bleach:
        try:
            return bleach.clean(html)
        except Exception:
            pass
    return html


def _html_to_markdown(html: str) -> str:
    """Convert HTML to markdown if html2text is available."""
    if html2text:
        try:
            conv = html2text.HTML2Text()
            conv.ignore_links = False
            return conv.handle(html)
        except Exception:
            pass
    return html


async def analyze_chat_for_actions(chat_history: str) -> Dict[str, Any]:
    """Parse chat history and suggest next actions.

    Uses OpenAI if configured, otherwise falls back to naive heuristics.
    """
    if openai and os.getenv("OPENAI_API_KEY"):
        openai.api_key = os.getenv("OPENAI_API_KEY")
        system_prompt = (
            "Analyze the following chat history and return a JSON object describing "
            "any actions the system should take. Include fields to gather from the "
            "user and the next recommended step."
        )
        try:
            resp = await openai.ChatCompletion.acreate(
                model=os.getenv("ANALYSIS_MODEL", "gpt-3.5-turbo"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": chat_history},
                ],
                temperature=0,
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:  # pragma: no cover - network failures
            logger.exception("LLM analysis failed: %s", e)

    # Fallback heuristic
    text = chat_history.lower()
    if "weather" in text:
        return {"actions": [{"tool": "weather.fake", "fields": ["location"]}]}
    if any(k in text for k in ["calc", "calculate", "+", "-"]):
        return {"actions": [{"tool": "calculator", "fields": ["expression"]}]}
    return {"actions": []}


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

SECRET_TOKEN = settings.ELEVENLABS_MCP_SECRET


@app.middleware("http")
async def auth_header(request: Request, call_next):
    if request.url.path.startswith("/mcp"):
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token != SECRET_TOKEN:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)


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


class NavigateReq(BaseModel):
    chat_history: str


@app.post("/api/navigate")
async def navigate(req: NavigateReq):
    """Analyze chat history and return suggested actions."""
    return await analyze_chat_for_actions(req.chat_history)


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


@app.get("/api/user/data")
async def get_user_data(request: Request):
    token = get_token(request)
    data = load_user_data(token)
    return data or {}


@app.post("/api/user/data")
async def post_user_data(request: Request):
    token = get_token(request)
    payload = await request.json()
    save_user_data(token, payload)
    return {"status": "saved"}


@app.delete("/api/user/data")
async def delete_user_data_endpoint(request: Request):
    token = get_token(request)
    delete_user_data(token)
    return {"status": "deleted"}


class EmbedReq(BaseModel):
    html: str
    plain: str
    sources: Optional[Any] = None


@app.post("/api/embed")
async def embed_snippet(req: EmbedReq):
    """Save a snippet and return sanitized markup and metadata."""
    sanitized = _sanitize_html(req.html)
    markdown = _html_to_markdown(req.html)
    snip_id = uuid.uuid4().hex[:8]
    url = f"/s/{snip_id}"
    db = sqlite3.connect(os.getenv("SNIPPET_DB", "snippets.sqlite3"))
    db.execute(
        "CREATE TABLE IF NOT EXISTS snippets (id TEXT PRIMARY KEY, html TEXT, plain TEXT, markdown TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    db.execute(
        "INSERT INTO snippets (id, html, plain, markdown) VALUES (?, ?, ?, ?)",
        (snip_id, sanitized, req.plain, markdown),
    )
    db.commit()
    db.close()
    return {"id": snip_id, "url": url, "sanitizedHtml": sanitized, "md": markdown}


@app.post("/mcp")
async def mcp_endpoint(request: Request):
    """Unified MCP endpoint supporting optional SSE."""
    accepts_sse = "text/event-stream" in request.headers.get("accept", "")
    payload = await request.json()
    is_batch = isinstance(payload, list)
    calls = payload if is_batch else [payload]
    results = []

    for call in calls:
        method = call.get("method")
        if method == "initialize":
            resp = await initialize(InitReq(**call))
        elif method == "tools/list":
            resp = await list_tools()
        elif method == "resources/list":
            resp = await list_resources()
        elif method and method.startswith("tool/") and method.endswith("/invoke"):
            tool_id = method.split("/")[1]
            resp = await invoke_tool(tool_id, InvokeReq(**call))
        else:
            resp = {"error": f"Unknown method {method}"}
        if isinstance(resp, JSONRPCResponse):
            results.append(resp.dict())
        else:
            results.append(resp)

    if accepts_sse:
        async def event_stream():
            for item in results:
                yield f"data: {json.dumps(item)}\n\n"
                await asyncio.sleep(0)
        if EventSourceResponse:
            return EventSourceResponse(event_stream())
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    return results if is_batch else results[0]


@app.get("/mcp")
async def mcp_keepalive():
    """Optional keep-alive SSE stream."""
    if EventSourceResponse:
        responder = EventSourceResponse
    else:
        def _sse(gen):
            return StreamingResponse(gen, media_type="text/event-stream")

        responder = _sse

    async def ping():
        while True:
            yield f"data: {json.dumps({'time': iso_now()})}\n\n"
            await asyncio.sleep(15)

    return responder(ping())


@app.get("/sse")
async def sse_bridge(request: Request):
    """Bridge SSE requests from /sse to /mcp."""
    # ElevenLabs sends SSE traffic to /sse, but our keepalive lives at /mcp.
    # A simple redirect is sufficient as their client follows 302 responses.
    return RedirectResponse(url="/mcp")


# ---------------------------------------------------------------------------
# Static UI
# ---------------------------------------------------------------------------

# Serve the web UI located in the "static" folder. The directory contains
# an index.html that interacts with the API via JavaScript.
app.mount("/", StaticFiles(directory="static", html=True), name="static")


def run_servers(api_port: int = 8000, ui_port: int | None = None) -> None:
    """Run FastAPI application."""
    port = int(os.getenv("PORT", str(api_port)))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")


if __name__ == "__main__":
    run_servers()

