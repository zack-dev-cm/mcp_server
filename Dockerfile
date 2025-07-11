FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx openai pydantic pydantic-settings sse-starlette cryptography
ENV ELEVENLABS_MCP_SECRET=$ELEVENLABS_MCP_SECRET
CMD ["python", "server.py"]
