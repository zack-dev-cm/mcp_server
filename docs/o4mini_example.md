# o4-mini Integration Example

This document demonstrates how to connect the hypothetical `o4-mini` language model
to the MCP server using a custom tool. We also create a sample tool that
provides synthetic company data and a minimal web page to interact with the
model.

## 1. Integration steps

1. **Create a plugin for the `o4-mini` model.**
   The plugin defines a new MCP tool that sends a request to the model's API
   endpoint and returns the generated text.
2. **Create a sample company database tool.**
   This tool exposes a small in-memory dataset that the model can query.
3. **Expose the tools via the existing MCP server.**
   When the server starts it automatically loads modules from the `plugins`
   directory, registering any tools defined with the `mcp_tool` decorator.
4. **Build a simple web page.**
   The page lets you enter a prompt, calls the `o4-mini` tool and displays the
   response.
5. **Run the server and open the page in your browser.**

## 2. Code snippets

### a. Connecting to the `o4-mini` model

```python
# plugins/o4mini_chat.py
import os
from fastapi import HTTPException
import httpx
from server import mcp_tool, ToolInput

# Endpoint of the o4-mini API
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
```

### b. Sample company database tool

```python
# plugins/company_db.py
from server import mcp_tool, ToolInput

COMPANIES = [
    {"id": 1, "name": "Acme Corp", "industry": "Manufacturing", "employees": 250},
    {"id": 2, "name": "Globex Inc", "industry": "Technology", "employees": 500},
    {"id": 3, "name": "Soylent Corp", "industry": "Food", "employees": 300},
]

@mcp_tool(
    "company.search",
    "Search the sample company database",
    [ToolInput(name="query", type="string", description="Name or industry")],
)
async def company_search_tool(params):
    term = params["query"].lower()
    matches = [c for c in COMPANIES if term in c["name"].lower() or term in c["industry"].lower()]
    return {"results": matches}
```

### c. Minimal web page

```html
<!-- static/o4mini_demo.html -->
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>o4-mini Demo</title>
</head>
<body>
  <h2>Ask the o4-mini model</h2>
  <input type="text" id="prompt" placeholder="Enter prompt" />
  <button id="send">Send</button>
  <pre id="reply"></pre>

  <script>
  document.getElementById('send').addEventListener('click', async () => {
      const prompt = document.getElementById('prompt').value;
      const resp = await fetch('/v1/tool/' + window.o4miniId + '/invoke', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: 1, method: 'invoke', params: {prompt}})
      });
      const data = await resp.json();
      document.getElementById('reply').textContent = data.result.reply;
  });

  // fetch tool list on load to discover the o4-mini tool ID
  fetch('/v1/tool').then(r => r.json()).then(list => {
      for (const item of list) {
          const id = Object.keys(item)[0];
          if (item[id].name === 'o4mini.chat') {
              window.o4miniId = id;
              break;
          }
      }
  });
  </script>
</body>
</html>
```

## 3. Sample prompts and outputs

Example prompt:

```
List companies in the technology industry.
```

Expected model workflow:
1. The `o4-mini` model receives the prompt.
2. It may call the `company.search` tool with the query `technology`.
3. The tool returns the matching record for `Globex Inc`.
4. The model replies with a description of that company.

## 4. Running the demo

1. Install dependencies and start the server:

```bash
pip install fastapi uvicorn httpx openai pydantic-settings
python server.py
```

2. Open `http://localhost:8000/o4mini_demo.html` in your browser.
3. Enter a prompt such as *"Tell me about companies in manufacturing"*.
4. The reply from the `o4-mini` model will appear below the button.

This setup shows how new tools can be combined with a model via the MCP server
and exposed through a simple webpage.
