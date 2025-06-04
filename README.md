# MCP Server

A minimal reference implementation of the Model Context Protocol (MCP) with a few mock tools and an optional Gradio playground.

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
