# MCP Server

A minimal reference implementation of the Model Context Protocol (MCP) with a few mock tools and an optional Gradio playground.

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/zack-dev-cm/mcp_server/blob/main/MCP_colab.ipynb)

## Usage

Run the server locally:

```bash
python server.py
```

Inside Google Colab or other notebooks use the helper:

```python
from colab_adapter import launch_in_colab
launch_in_colab()
```

The API is served on port `8000` by default and the Gradio UI will try to use `GRADIO_SERVER_PORT` or the first free port starting at 7860.

## Run in Google Colab

Open [`MCP_colab.ipynb`](./MCP_colab.ipynb) in Colab or click the badge above and run the cells.

If starting from a blank notebook, run these commands to set up and launch the
server:

```python
!git clone https://github.com/zack-dev-cm/mcp_server.git
%cd /content/mcp_server
!pip install fastapi uvicorn[standard] gradio==4.* pydantic python-dotenv
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

If running locally, install the `openai` package first:

```bash
pip install openai
python server.py
```

The Dockerfile installs `openai` automatically. Invoke the `openai.chat` or `openai.vision` tools via the API or Gradio UI.

## Deploying to Cloud Run

You can deploy the server on [Google Cloud Run](https://cloud.google.com/run)
using the provided `Dockerfile`:

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
