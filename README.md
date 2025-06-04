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

Install dependencies (only needed once):

```python
!pip install fastapi uvicorn[standard] gradio==4.* pydantic python-dotenv
```

Start the servers and keep the notebook cell alive:

```python
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
