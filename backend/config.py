import logging

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://autopilot:changeme@localhost:5432/content_autopilot"
    sync_database_url: str = "postgresql://autopilot:changeme@localhost:5432/content_autopilot"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM APIs
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    litellm_base_url: str | None = None
    litellm_api_key: str | None = None
    requesty_api_key: str | None = None

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
    prompt_nc_base_path: str = (
        "/zukunftsbund/projekte/content-autopilot/datensammlung/prompts-skills/"
    )

    # Storage-Backend: "localfs" (Standard) oder "nc" (Nextcloud, deprecated)
    prompt_storage_backend: str = "localfs"
    # Basisverzeichnis fuer lokales Dateisystem-Backend (content-truth/)
    content_truth_base_path: str = "/app/content-truth"
    # Beschreibbares Overlay fuer Prompt-Studio-Edits (gitignored, ./data-Mount)
    # ENV: CONTENT_TRUTH_OVERLAY_PATH
    content_truth_overlay_path: str = "/app/data/prompts-custom"

    # VoiceScriptor
    voicescriptor_bot_token: str | None = None
    voicescriptor_chat_id: str | None = None

    # Pipeline Throttle (#156)
    max_calls_per_tenant_per_hour: int = 200
    max_calls_global_per_hour: int = 1000

    # Quality-Gate (#38 Chunk 3) — Final-Gate vor Telegram-Versand.
    # False (Shadow-Mode, Default): Gate läuft immer, loggt Telemetrie, blockiert NIE.
    # True (Enforce-Mode): bei not passed → Review-Queue-Pfad statt Roh-Versand.
    # ENV: QUALITY_GATE_ENFORCE=true aktiviert den Enforce-Modus.
    quality_gate_enforce: bool = False

    # Telegram Bot (Content-Autopilot)
    telegram_bot_token: str | None = None
    telegram_admin_chat_id: str | None = None  # TELEGRAM_ADMIN_CHAT_ID env var
    telegram_webhook_secret: str | None = None
    telegram_bot_username: str | None = "content_autopilot_bot"

    # WhatsApp Business Cloud API (Phase 8.1, #140)
    # Setup: Meta-Developer-Account → WhatsApp-Business-App → Phone-Number-ID
    # WHATSAPP_ACCESS_TOKEN: Long-lived Access Token vom Meta-Dashboard
    # WHATSAPP_PHONE_NUMBER_ID: Phone Number ID des verbundenen Bots
    # WHATSAPP_VERIFY_TOKEN: selbstgewählt für Webhook-Verifikation
    whatsapp_access_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_verify_token: str | None = None
    whatsapp_app_secret: str | None = None  # für X-Hub-Signature-256-Verifikation

    # Admin-Login (Issue #98 — Admin-Tool Port 8602)
    # Werte kommen aus .env (Server), nie aus Git.
    # ADMIN_USER: Benutzername für die Admin-Login-Seite
    # ADMIN_PASSWORD: Passwort (Klartext in .env, nie loggen, nie in Code)
    # ADMIN_SESSION_SECRET: HMAC-Schlüssel für signierte Session-Tokens
    #   Wenn unset, wird der Secret aus default_tenant_key abgeleitet (weniger sicher).
    admin_user: str | None = None
    admin_password: str | None = None
    admin_session_secret: str | None = None

    # SMTP für Magic-Link-Login (W3). Kein Host → Link wird nur geloggt (dev-Fallback).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "noreply@zukunftsbund.de"
    # COOKIE_SECURE: Secure-Flag für Session-/CSRF-Cookies. Default False (HTTP-über-VPN);
    #   auf true setzen, sobald hinter HTTPS deployt wird.
    cookie_secure: bool = False

    @model_validator(mode="after")
    def _warn_on_insecure_production(self):
        """Sicherheits-Selbstcheck beim Start (W1, 2026-07-21).

        Warnt laut, wenn in Produktion unsichere Defaults aktiv sind — statt sie
        still zu akzeptieren. Bricht NICHT (dev/VPN-Setups bleiben lauffähig), macht
        die Lücken aber im Log sichtbar, damit sie vor echtem Kundenbetrieb zu sind.
        """
        if self.app_env == "production":
            log = logging.getLogger(__name__)
            if not self.cookie_secure:
                log.warning(
                    "[Security] COOKIE_SECURE=false in production — Session-/CSRF-Cookies "
                    "werden ohne Secure-Flag gesetzt. Auf true stellen, sobald hinter HTTPS."
                )
            if self.default_tenant_key == "default-key":
                log.warning(
                    "[Security] DEFAULT_TENANT_KEY ist der unsichere Standardwert in "
                    "production — Fernet-Verschlüsselung nutzt einen bekannten Schlüssel. "
                    "Dediziertes DEFAULT_TENANT_KEY in .env setzen."
                )
            if not self.admin_session_secret:
                log.warning(
                    "[Security] ADMIN_SESSION_SECRET nicht gesetzt in production — "
                    "Admin-Login wird fail-closed abgelehnt, bis es konfiguriert ist."
                )
        return self

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
