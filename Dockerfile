FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir fastapi uvicorn[standard] gradio==4.* pydantic openai
CMD ["python", "server.py"]
