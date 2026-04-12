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

    yield


app = FastAPI(title="Content-Autopilot", version="2.0.0", lifespan=lifespan)

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

app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])
app.include_router(sources_router, prefix="/api", tags=["Sources"])
app.include_router(items_router, prefix="/api", tags=["Items"])
app.include_router(content_router, prefix="/api", tags=["Content"])
app.include_router(campaigns_router, prefix="/api", tags=["Campaigns"])
app.include_router(tenants_router, prefix="/api", tags=["Tenants"])
app.include_router(activity_router, prefix="/api", tags=["Activity"])
app.include_router(ideas_router, prefix="/api", tags=["Ideas"])
app.include_router(feedback_router, prefix="/api", tags=["Feedback"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
