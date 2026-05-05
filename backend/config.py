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
    requesty_api_key: Optional[str] = None

    # Nextcloud
    nextcloud_url: str = ""
    nextcloud_user: str = ""
    nextcloud_password: str = ""

    # App
    # Note: this is the default/fallback tenant key, unrelated to ZFB/ZKG tenant keys
    # ZKG tenant key: ***REMOVED-TENANT-KEY-ZKG*** (old ZFB key ***REMOVED-TENANT-KEY*** kept as secondary until 2026-08-01)
    default_tenant_key: str = "default-key"

    # Sentry
    sentry_dsn: str = ""  # Empty = disabled
    app_env: str = "production"  # dev | staging | production

    # Storage paths (Nextcloud)
    brand_voice_nc_base_path: str = "/content-autopilot/v2/Kunde/"
    prompt_nc_base_path: str = "/zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/"

    # VoiceScriptor
    voicescriptor_bot_token: Optional[str] = None
    voicescriptor_chat_id: Optional[str] = None

    # Pipeline Throttle (#156)
    max_calls_per_tenant_per_hour: int = 200
    max_calls_global_per_hour: int = 1000

    # Telegram Bot (Content-Autopilot)
    telegram_bot_token: Optional[str] = None
    telegram_admin_chat_id: Optional[str] = None  # TELEGRAM_ADMIN_CHAT_ID env var
    telegram_webhook_secret: Optional[str] = None
    telegram_bot_username: Optional[str] = "content_autopilot_bot"

    # WhatsApp Business Cloud API (Phase 8.1, #140)
    # Setup: Meta-Developer-Account → WhatsApp-Business-App → Phone-Number-ID
    # WHATSAPP_ACCESS_TOKEN: Long-lived Access Token vom Meta-Dashboard
    # WHATSAPP_PHONE_NUMBER_ID: Phone Number ID des verbundenen Bots
    # WHATSAPP_VERIFY_TOKEN: selbstgewählt für Webhook-Verifikation
    whatsapp_access_token: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_verify_token: Optional[str] = None
    whatsapp_app_secret: Optional[str] = None  # für X-Hub-Signature-256-Verifikation

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
