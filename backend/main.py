import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from sqlalchemy import select, text

import logging_config
logging_config.setup_logging()

import sentry_config
sentry_config.init_sentry()

from config import settings
from models import async_session_factory, Tenant

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run alembic migrations on startup
    import subprocess
    logger.info("Running database migrations...")
    try:
        subprocess.run(["alembic", "upgrade", "head"], check=True, cwd="/app", timeout=30)
    except Exception as e:
        logger.warning(f"Migration failed (may already be applied): {e}")

    # Create default tenant if not exists (check both primary and secondary key)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Tenant).where(
                (Tenant.api_key == settings.default_tenant_key) |
                (Tenant.api_key_secondary == settings.default_tenant_key)
            )
        )
        tenant = result.scalars().first()
        if not tenant:
            tenant = Tenant(
                name="Default Tenant",
                api_key=settings.default_tenant_key,
                settings={"tone": "professionell, informativ, mit persoenlicher Note", "language": "de"},
            )
            session.add(tenant)
            await session.commit()
            logger.info("Default tenant created (API key configured via env)")

        # Auto-setup default project if none exists
        from models.project import Project
        existing_projects = await session.execute(select(Project).where(Project.tenant_id == tenant.id))
        if not existing_projects.scalars().first():
            default_project = Project(
                tenant_id=tenant.id,
                name="Standard",
                slug="standard",
                description="Standard-Projekt",
            )
            session.add(default_project)
            await session.commit()
            logger.info("Default project 'Standard' created")

            # Assign existing sources to default project
            from models.source import Source
            await session.execute(
                Source.__table__.update().where(
                    Source.tenant_id == tenant.id, Source.project_id == None
                ).values(project_id=default_project.id)
            )
            await session.commit()

        # Auto-setup Requesty.ai provider if REQUESTY_API_KEY is set and no providers exist
        if settings.requesty_api_key and tenant:
            from models.llm_provider import LLMProvider
            existing = await session.execute(select(LLMProvider).where(LLMProvider.tenant_id == tenant.id))
            if not existing.scalars().first():
                from api.llm_settings import _encrypt_key
                provider = LLMProvider(
                    tenant_id=tenant.id,
                    name="Requesty.ai",
                    provider_type="requesty",
                    api_key_encrypted=_encrypt_key(settings.requesty_api_key),
                    base_url="https://router.eu.requesty.ai/v1",
                    model_name="vertex/gemini-2.5-flash-lite@europe-central2",
                    task_assignment="all",
                    is_default=True,
                    is_active=True,
                )
                session.add(provider)
                await session.commit()
                logger.info("Auto-configured Requesty.ai as default LLM provider")

    # Register Telegram webhook if token configured
    if settings.telegram_bot_token and settings.telegram_webhook_secret:
        try:
            import httpx, os
            webhook_url = os.environ.get("TELEGRAM_WEBHOOK_URL", "")
            if webhook_url:
                resp = httpx.post(
                    f"https://api.telegram.org/bot{settings.telegram_bot_token}/setWebhook",
                    json={"url": webhook_url, "secret_token": settings.telegram_webhook_secret},
                    timeout=10,
                )
                if resp.json().get("ok"):
                    logger.info(f"Telegram webhook registered: {webhook_url}")
                else:
                    logger.warning(f"Telegram webhook registration failed: {resp.text}")
        except Exception as e:
            logger.warning(f"Telegram webhook setup skipped: {e}")

    yield


app = FastAPI(title="Content-Autopilot", version="2.0.0", lifespan=lifespan)

# CORS — needed for Cowork dashboard and external integrations
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-CSRF-Token"],
)

# CSRF — Double-Submit Cookie pattern (exempt: X-API-Key requests, Telegram webhook)
from middleware.csrf_middleware import CSRFMiddleware
app.add_middleware(CSRFMiddleware)

# Structured JSON logging middleware — sets correlation_id / tenant_id context
from middleware.logging_middleware import LoggingMiddleware
app.add_middleware(LoggingMiddleware)

# Import and include routers
from api.dashboard import router as dashboard_router
from api.sources import router as sources_router
from api.items import router as items_router
from api.content import router as content_router
from api.campaigns import router as campaigns_router
from api.tenants import router as tenants_router
from api.activity import router as activity_router
from api.ideas import router as ideas_router
from api.feedback import router as feedback_router
from api.llm_settings import router as llm_settings_router

app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])
app.include_router(sources_router, prefix="/api", tags=["Sources"])
app.include_router(items_router, prefix="/api", tags=["Items"])
app.include_router(content_router, prefix="/api", tags=["Content"])
app.include_router(campaigns_router, prefix="/api", tags=["Campaigns"])
app.include_router(tenants_router, prefix="/api", tags=["Tenants"])
app.include_router(activity_router, prefix="/api", tags=["Activity"])
app.include_router(ideas_router, prefix="/api", tags=["Ideas"])
app.include_router(feedback_router, prefix="/api", tags=["Feedback"])
app.include_router(llm_settings_router, prefix="/api", tags=["Settings"])

from api.scheduling import router as scheduling_router
app.include_router(scheduling_router, prefix="/api", tags=["Scheduling"])

from api.carousels import router as carousels_router
app.include_router(carousels_router, prefix="/api", tags=["Carousels"])

from api.projects import router as projects_router
app.include_router(projects_router, prefix="/api", tags=["Projects"])

from api.content_dna import router as content_dna_router
app.include_router(content_dna_router, prefix="/api", tags=["ContentDNA"])

from api.pipeline import router as pipeline_router
app.include_router(pipeline_router, prefix="/api", tags=["Pipeline"])

from api.dialogue import router as dialogue_router
app.include_router(dialogue_router, prefix="/api", tags=["Dialogue"])

from api.cowork import router as cowork_router
app.include_router(cowork_router, tags=["Cowork"])

from api.quality import router as quality_router
app.include_router(quality_router, prefix="/api", tags=["Quality"])

from services.ws_manager import ws_router
app.include_router(ws_router, tags=["WebSocket"])

from api.brand_voice import router as brand_voice_router
app.include_router(brand_voice_router, prefix="/api", tags=["BrandVoice"])

from api.voice_feedback import router as voice_feedback_router
app.include_router(voice_feedback_router, prefix="/api", tags=["VoiceFeedback"])

from api.wizard import router as wizard_router
app.include_router(wizard_router, prefix="/api", tags=["Wizard"])

from api.admin import router as admin_router
app.include_router(admin_router, prefix="/api", tags=["Admin"])

from api.reservoir import router as reservoir_router
app.include_router(reservoir_router, prefix="/api", tags=["Reservoir"])

from api.telegram import router as telegram_router
app.include_router(telegram_router, prefix="/api", tags=["Telegram"])

from api.whatsapp import router as whatsapp_router
app.include_router(whatsapp_router, prefix="/api", tags=["WhatsApp"])

from api.analytics import router as analytics_router
app.include_router(analytics_router, prefix="/api", tags=["Analytics"])


@app.get("/api/health")
async def health():
    import asyncio
    import redis as redis_lib
    from models.base import async_engine
    from fastapi.responses import JSONResponse

    checks = {}
    overall = "ok"

    # DB check
    try:
        async with async_engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3.0)
        checks["db"] = "ok"
    except Exception as e:
        logger.warning("DB health check failed: %s", e)
        checks["db"] = "error: connection failed"
        overall = "degraded"

    # Redis check (async — kein Event-Loop-Blocking)
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
        await asyncio.wait_for(r.ping(), timeout=3.0)
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as e:
        logger.warning("Redis health check failed: %s", e)
        checks["redis"] = "error: connection failed"
        overall = "degraded"

    # NC Storage check (optional, timeout 5s)
    try:
        from services.brand_voice_storage import get_default_nc_adapter
        adapter = get_default_nc_adapter()
        # stat() the root path — fast check without reading file content
        adapter.stat("/")
        checks["storage_adapter"] = "ok"
    except Exception as e:
        logger.warning("Storage health check failed: %s", e)
        checks["storage_adapter"] = "degraded: unreachable"
        # NC degraded does NOT make overall status degraded (NC can be down without breaking core)

    status_code = 200 if overall == "ok" else 503
    return JSONResponse(
        {"status": overall, "version": "2.0.0", "checks": checks},
        status_code=status_code,
    )


@app.get("/api/csrf-token")
async def get_csrf_token(response: Response):
    """Issue a CSRF token — sets cookie + returns token in body.

    Frontend: call once on load, store token, include as X-CSRF-Token header
    on state-changing requests. Cookie is SameSite=Strict to prevent leakage.
    """
    from middleware.csrf_middleware import generate_csrf_token, CSRF_COOKIE, TOKEN_TTL
    token = generate_csrf_token()
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        max_age=TOKEN_TTL,
        httponly=False,       # Frontend JS needs to read it
        samesite="strict",
        secure=False,         # Set to True when HTTPS is enabled
    )
    return {"csrf_token": token}


@app.get("/api/_test/sentry-error")
async def sentry_test_error():
    """Dev-only: Trigger a test Sentry event to verify integration."""
    from config import settings as _s
    if _s.app_env not in ("dev", "development", "staging"):
        from fastapi import HTTPException
        raise HTTPException(404, "Not found")
    raise RuntimeError("Sentry test error — intentional from /api/_test/sentry-error")
