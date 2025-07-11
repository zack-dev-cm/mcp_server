FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN apt-get update \
    && apt-get install -y ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] pydantic openai sse-starlette cryptography \
    pydub ffmpeg-python aiofiles httpx pydantic-settings
ENV ELEVENLABS_MCP_SECRET=$ELEVENLABS_MCP_SECRET
CMD ["python", "server.py"]
