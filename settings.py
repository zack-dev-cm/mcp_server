from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    ELEVENLABS_MCP_SECRET: str = Field(..., env="ELEVENLABS_MCP_SECRET")

settings = Settings()
