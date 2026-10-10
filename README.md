# MCP Server

A minimal reference implementation of the Model Context Protocol (MCP) with a few mock tools and an optional Gradio playground.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/zack-dev-cm/mcp_server/blob/main/MCP_colab.ipynb)

## Usage

Install the local demo and test dependencies, then run the server:

```bash
python -m pip install -r requirements-test.txt
export ELEVENLABS_MCP_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python server.py
```

Create a `dev.env` file and add your OpenAI API key:

```bash
OPENAI_API_KEY=your-openai-key
```

Inside Google Colab or other notebooks use the helper:

```python
from colab_adapter import launch_in_colab
launch_in_colab()
```

`ELEVENLABS_MCP_SECRET` is required by the server. Store a stable value privately
for later starts and configure clients using `/mcp` with that bearer secret.
The example above creates a temporary local value without printing it.

The API is served on port `8000` by default and the Gradio UI will try to use `GRADIO_SERVER_PORT` or the first free port starting at 7860.

Open `/` for resources, tools and echo chat, or `/examples.html` for the three
demo actions. Weather values are randomly generated. Failed requests are shown
on the page; controls become available again for retry. Chat and resource text
are rendered literally, including strings that look like HTML.

The calculator accepts numbers, parentheses and `+`, `-`, `*`, `/`, `//`, `%`
and `**`. Expressions are limited to 256 characters, 128 syntax nodes and 16
nested operations. Numbers and intermediate results must be finite and no
larger than `1e12` in absolute value; exponents range from `-12` to `12`.
Python attributes, calls, names and comprehensions are rejected with HTTP 400.

## Run in Google Colab

Open [`MCP_colab.ipynb`](./MCP_colab.ipynb) in Colab or click the badge above and run the cells.

If starting from a blank notebook, run these commands to set up and launch the
server:

```python
!git clone https://github.com/zack-dev-cm/mcp_server.git
%cd /content/mcp_server
!pip install fastapi uvicorn[standard] gradio==4.* pydantic python-dotenv \
            httpx openai pydantic-settings cryptography==50.0.2
from colab_adapter import launch_in_colab
launch_in_colab()
```

You can now query the API from another cell:

```python
import requests, time
time.sleep(2)
print(requests.get("http://localhost:8000/v1/resources").json())
```

The server output shows a public URL for the Gradio interface so you can try the demo visually.

## LLM/VLM Plugin Example

Plugins can extend the server with new tools. The included `openai_chat` and `openai_vision` plugins show how to call OpenAI models. Set `OPENAI_API_KEY` in your environment and start the server.

If running locally, install the required packages first:

```bash
pip install openai httpx pydantic-settings cryptography==50.0.2
python server.py
```

The Dockerfile installs `openai` automatically. Invoke the `openai.chat` or `openai.vision` tools via the API or Gradio UI.

## Streamable HTTP Endpoint

ChatGPT connectors can talk directly to the server using the unified `/mcp` route.
Send JSON‑RPC requests with `POST /mcp` to receive standard JSON responses. When
your client supports Server‑Sent Events you may instead `GET /mcp` and keep the
connection open to stream updates.

Configure your ChatGPT connector to point at your server’s base URL and use the
`/mcp` endpoint for both non‑streaming and streaming interactions.

## User Data API

Authenticated sessions can store and manage user‑specific JSON payloads.
Before using these endpoints, set `MASTER_KEY` to a generated Fernet key in the
server environment. There is no default key. Keep this key private and stable
across restarts. `USERDATA_DB` selects the database path and defaults to
`user_store/data.db` beside `secure_store.py`.

Existing databases need the explicit migration described in
[User-data storage and migration](docs/user-data-storage.md). Do not deploy
this storage change over legacy rows without completing that procedure.

After configuring storage, request a session ID and pass it as a bearer token:

```bash
# create a session and grab the token
TOKEN=$(curl -s -X POST http://localhost:8000/v1/initialize \
  -H 'Content-Type: application/json' \
  -d '{"id":1,"jsonrpc":"2.0","method":"initialize","params":{}}' \
  | jq -r '.result.sessionId')

# store data
curl -X POST http://localhost:8000/api/user/data \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"foo":"bar"}'

# fetch it back
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/user/data

# remove it
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/user/data
```

Stored JSON values round trip exactly, including `null`, `false`, `0`, empty
strings and empty arrays. A missing row returns `{}`. Invalid storage
configuration returns HTTP 503, legacy rows return 409 until migration, and
unverifiable rows return 500 without exposing their contents. Nonfinite JSON
values are rejected with 422. The current demo identifies data by its
in-memory session token; durable accounts and sessions are separate work.

Sessions are valid only in the process that created them. After a restart,
the same bearer token returns 401 even if the database and encryption key are
retained. A new session cannot retrieve the previous session's row. Another
worker also rejects that token. This API currently supports session-local demo
use; it has not qualified recovery of existing users' data after migration.

## Deploying to Cloud Run

You can deploy the server on [Google Cloud Run](https://cloud.google.com/run)
using the provided `Dockerfile`:

Configure `ELEVENLABS_MCP_SECRET` and `MASTER_KEY` through the deployment's
secret mechanism. Cloud Run's default writable filesystem loses data when an
instance stops. A selected storage backend must establish durability and
supported SQLite locking, and the HTTP session behavior above must meet the
intended use. These commands alone do not qualify protected storage or user
access after restart. Follow the [release qualification](docs/user-data-storage.md#release-qualification)
before replacing an existing service.

```bash
# build and push the container
gcloud builds submit --tag gcr.io/PROJECT_ID/mcp-server

# deploy the image to Cloud Run
gcloud run deploy mcp-server \
  --image gcr.io/PROJECT_ID/mcp-server \
  --region REGION \
  --allow-unauthenticated
```

Cloud Run sets the `PORT` environment variable automatically, which the server
uses to expose both the API and Gradio UI on the same endpoint.

## Running Tests

Run the repository tests in an isolated environment:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q
```

Fixtures use temporary SQLite databases, generated test keys and a synthetic
MCP secret. Outbound network connections are blocked. Do not source real
provider keys for this suite. These tests cover local storage and API behavior;
they do not verify OpenAI plugins, Gradio, a deployed endpoint or MCP client
interoperability. Ubuntu CI runs the same suite on Python 3.10 and 3.12.

## Browser checks

After installing the local test dependencies above, install the browser test
runner and Chromium:

```bash
npm ci
npx playwright install chromium --only-shell
npm run test:browser
```

The runner starts a loopback FastAPI server with the provider key disabled.
It checks real resource, arithmetic, echo and demo weather flows, then injects
HTTP, network and protocol failures to check error display and retry. It also
checks literal rendering of HTML-like input and duplicate-click handling.
The checks do not exercise Gradio, external providers, `/mcp` interoperability
or a deployed service. `DEMO_TEST_PORT` can select another free local port.
