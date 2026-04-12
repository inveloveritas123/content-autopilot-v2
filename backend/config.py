from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://autopilot:changeme@localhost:5432/content_autopilot"
    sync_database_url: str = "postgresql://autopilot:changeme@localhost:5432/content_autopilot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM APIs
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    litellm_base_url: Optional[str] = None
    litellm_api_key: Optional[str] = None

    # Nextcloud
    nextcloud_url: str = ""
    nextcloud_user: str = ""
    nextcloud_password: str = ""

    # App
    default_tenant_key: str = "default-key"

    # VoiceScriptor
    voicescriptor_bot_token: Optional[str] = None
    voicescriptor_chat_id: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
