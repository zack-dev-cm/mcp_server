"""
For colab run
MCP (Model Context Protocol) Reference Implementation – June 2025
=================================================================
**Colab‑friendly** version that avoids the classic *“asyncio.run() cannot be
called from a running event loop”* error and plays nicely with IPython’s
already‑running loop.

*   FastAPI server exposing core MCP endpoints (2025‑03‑26 spec).
*   In‑memory registries for resources, tools and prompts.
*   Four **mock tools** (echo, calculator, weather, file.search).
*   **Gradio** playground UI.

Author: @kaisenaiko • Updated: 2025‑06‑04
"""

# ──────────────────────────────────────────────────────────────────────────
# 0. Imports & Package Setup
# ──────────────────────────────────────────────────────────────────────────

# To run the first time in Colab, uncomment the next line:
# !pip install fastapi uvicorn[standard] gradio==4.* nest_asyncio pydantic python-dotenv --quiet

import json, uuid, logging, asyncio, datetime as dt, random, itertools, time, threading
from typing import Dict, List, Any, Optional, Union

# Core deps
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn, gradio as gr

# Colab/IPython event‑loop patch
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    # If user forgot to pip install, we can still limp along; the fallback
    # in the entry‑point will create a background thread.
    nest_asyncio = None

# ──────────────────────────────────────────────────────────────────────────
# 1. Constants & Helpers
# ──────────────────────────────────────────────────────────────────────────

PROTOCOL_VERSION = "2025-03-26"
SERVER_ID = f"mcp-demo-{uuid.uuid4()}"
START_TIME = dt.datetime.utcnow()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("mcp")

iso_now = lambda: dt.datetime.utcnow().isoformat() + "Z"

# ──────────────────────────────────────────────────────────────────────────
# 2. JSON‑RPC Models
# ──────────────────────────────────────────────────────────────────────────

class JSONRPCError(BaseModel):
    code: int; message: str; data: Optional[Any] = None

class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"; id: Union[str, int, None]
    result: Optional[Any] = None; error: Optional[JSONRPCError] = None

# ──────────────────────────────────────────────────────────────────────────
# 3. MCP Domain Models
# ──────────────────────────────────────────────────────────────────────────

class Resource(BaseModel):
    uri: str; description: str; metadata: Dict[str, Any] = Field(default_factory=dict)

class ToolInput(BaseModel):
    name: str; type: str; description: str; required: bool = True

class Tool(BaseModel):
    id: str; name: str; description: str; inputs: List[ToolInput]
    examples: List[Dict[str, Any]] = Field(default_factory=list); handler: Any = None

class Prompt(BaseModel):
    id: str; name: str; description: str; template: str

class Session(BaseModel):
    session_id: str; created: str; client_version: str

# ──────────────────────────────────────────────────────────────────────────
# 4. In‑memory Registries
# ──────────────────────────────────────────────────────────────────────────

resources: Dict[str, Resource] = {}
tools: Dict[str, Tool] = {}
prompts: Dict[str, Prompt] = {}
sessions: Dict[str, Session] = {}

# Decorator to register tools ------------------------------------------------

def mcp_tool(name: str, description: str, inputs: List[ToolInput]):
    def decorator(fn):
        tool_id = str(uuid.uuid4())
        tools[tool_id] = Tool(id=tool_id, name=name, description=description,
                              inputs=inputs, handler=fn)
        return fn
    return decorator

# ──────────────────────────────────────────────────────────────────────────
# 5. Mock Tool Implementations
# ──────────────────────────────────────────────────────────────────────────

@mcp_tool("echo", "Echo back text", [ToolInput(name="text", type="string", description="Text to echo")])
async def echo_tool(p):
    return {"echo": p["text"], "timestamp": iso_now()}

@mcp_tool("calculator", "Simple arithmetic eval", [ToolInput(name="expression", type="string", description="e.g. '2 + 2'")])
async def calculator_tool(p):
    try:
        return {"result": eval(p["expression"], {"__builtins__": {}})}
    except Exception as e:
        raise HTTPException(400, str(e))

@mcp_tool("weather.fake", "Random weather", [ToolInput(name="location", type="string", description="City/coords")])
async def weather_tool(p):
    return {"location": p["location"], "temperature_c": round(random.uniform(15, 30), 1),
            "condition": random.choice(["sunny", "cloudy", "rainy", "windy"]),
            "observed": iso_now()}

@mcp_tool("file.search", "Search resource descriptions", [ToolInput(name="query", type="string", description="Keyword")])
async def file_search_tool(p):
    term = p["query"].lower()
    hits = [r for r in resources.values() if term in r.description.lower()]
    return {"matches": [r.dict() for r in hits]}

# ──────────────────────────────────────────────────────────────────────────
# 6. Populate Sample Resources & Prompts
# ──────────────────────────────────────────────────────────────────────────

resources["memory://welcome-note"] = Resource(
    uri="memory://welcome-note",
    description="Welcome note explaining how to use the demo MCP server",
    metadata={"author": "system", "created": iso_now()})

prompts["hello-world"] = Prompt(
    id="hello-world", name="Hello World",
    description="Greets the user", template="You are a helpful AI. Greet the user.")

# ──────────────────────────────────────────────────────────────────────────
# 7. FastAPI Application Setup
# ──────────────────────────────────────────────────────────────────────────

app = FastAPI(title="MCP Demo Server", version=PROTOCOL_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"], allow_credentials=True)

@app.exception_handler(Exception)
async def universal_error(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(500, {"error": str(exc)})

# ─── Health & Static Endpoints ────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "uptime": str(dt.datetime.utcnow()-START_TIME), "now": iso_now()}

@app.get("/v1/resources")
async def list_resources():
    return [r.dict() for r in resources.values()]

@app.get("/v1/tool")
async def list_tools():
    return [{tid: t.dict(exclude={"handler"})} for tid, t in tools.items()]

@app.get("/v1/prompts")
async def list_prompts():
    return [p.dict() for p in prompts.values()]

# ─── Initialize & Tool Invoke (JSON‑RPC style) ────────────────────────────

class InitReq(BaseModel): id: Union[str,int]; jsonrpc:str="2.0"; method:str="initialize"; params:Dict[str,Any]

@app.post("/v1/initialize")
async def initialize(req: InitReq):
    sess_id = str(uuid.uuid4())
    sessions[sess_id] = Session(session_id=sess_id, created=iso_now(),
                                client_version=req.params.get("version","unknown"))
    return JSONRPCResponse(id=req.id, result={"serverId":SERVER_ID,"protocolVersion":PROTOCOL_VERSION,
                                             "sessionId":sess_id,"serverTime":iso_now()})

class InvokeReq(BaseModel): id:Union[str,int]; jsonrpc:str="2.0"; method:str; params:Dict[str,Any]

@app.post("/v1/tool/{tool_id}/invoke")
async def invoke_tool(tool_id:str, req:InvokeReq):
    if tool_id not in tools: raise HTTPException(404, "Tool not found")
    result = await tools[tool_id].handler(req.params)
    return JSONRPCResponse(id=req.id, result=result)

# ──────────────────────────────────────────────────────────────────────────
# 8. Gradio Playground
# ──────────────────────────────────────────────────────────────────────────

with gr.Blocks(title="MCP Demo UI") as demo:
    gr.Markdown("""## MCP Demo – Gradio UI
Use the tabs to explore resources, invoke tools, or chat via the echo tool.""")

    with gr.Tabs():
        with gr.TabItem("Resources"):
            df = gr.Dataframe(headers=["URI","Description"], datatype=["str","str"], interactive=False)
            gr.Button("Refresh").click(lambda: [[r.uri,r.description] for r in resources.values()],None,df)
            df.value = [[r.uri,r.description] for r in resources.values()]

        with gr.TabItem("Tools"):
            dd = gr.Dropdown(choices=[(t.name,tid) for tid,t in tools.items()], label="Tool")
            param = gr.JSON(label="Params (JSON)")
            out = gr.JSON()
            async def run_tool(tid,p):
                return await tools[tid].handler(p)
            gr.Button("Run").click(run_tool,[dd,param],out)

        with gr.TabItem("Chat"):
            chat = gr.Chatbot()
            msg = gr.Textbox()
            async def echo_chat(user, hist):
                hist = hist or []
                res = await echo_tool({"text":user})
                return hist+[[user,json.dumps(res,indent=2)]], ""
            gr.Button("Send").click(echo_chat,[msg,chat],[chat,msg])

# ──────────────────────────────────────────────────────────────────────────
# 9. Launch Helpers (FastAPI + Gradio concurrently)
# ──────────────────────────────────────────────────────────────────────────

async def _serve_fastapi(port=8000):
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info", lifespan="off")
    server = uvicorn.Server(config)
    await server.serve()

async def _serve_gradio(port=7860):
    demo.launch(server_name="0.0.0.0", server_port=port, show_error=True, share=True)

async def launch_servers():
    await asyncio.gather(_serve_fastapi(), _serve_gradio())

# ──────────────────────────────────────────────────────────────────────────
# 10. Colab‑friendly Entrypoint (no nested‑loop crash!)
# ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting MCP demo server…")

    def _start_in_thread():
        asyncio.run(launch_servers())  # runs in its *own* loop, no conflict

    # If we're already inside an event loop (e.g. Colab/IPython), spawn background thread.
    try:
        asyncio.get_running_loop()
        threading.Thread(target=_start_in_thread, daemon=True).start()
        # Keep main thread alive so notebook cell doesn’t terminate.
        for _ in itertools.count(): time.sleep(3600)
    except RuntimeError:
        # Not inside a running loop ➜ safe to run directly.
        asyncio.run(launch_servers())
