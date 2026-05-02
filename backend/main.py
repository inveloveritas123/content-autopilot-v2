import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from config import settings
from models import async_session_factory, Tenant

logging.basicConfig(level=logging.INFO)
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

    # Create default tenant if not exists
    async with async_session_factory() as session:
        result = await session.execute(select(Tenant).where(Tenant.api_key == settings.default_tenant_key))
        tenant = result.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                name="Default Tenant",
                api_key=settings.default_tenant_key,
                settings={"tone": "professionell, informativ, mit persoenlicher Note", "language": "de"},
            )
            session.add(tenant)
            await session.commit()
            logger.info(f"Default tenant created with API key: {settings.default_tenant_key}")

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

    yield


app = FastAPI(title="Content-Autopilot", version="2.0.0", lifespan=lifespan)

# CORS — needed for Cowork dashboard and external integrations
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

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


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
