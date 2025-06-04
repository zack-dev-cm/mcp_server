# MCP Tool Plugins

Tools placed in this folder are automatically imported when the server starts. Each module should use the `mcp_tool` decorator to register new tools.

Example plugins included:
- `openai_chat.py` – text chat completion using OpenAI models
- `openai_vision.py` – basic image understanding via OpenAI vision models

Set `OPENAI_API_KEY` in your environment for these plugins.

