import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.base import async_session_factory
from models.tenant import Tenant
from services.llm import set_llm_tenant
from services.rls import set_rls_tenant


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


async def get_tenant(x_api_key: str = Header(...), db: AsyncSession = Depends(get_db)) -> Tenant:
    result = await db.execute(
        select(Tenant).where(
            (Tenant.api_key == x_api_key) | (Tenant.api_key_secondary == x_api_key)
        )
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not tenant.enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "tenant_disabled",
                "reason": tenant.disabled_reason or "Tenant ist deaktiviert",
                "since": tenant.disabled_at.isoformat() if tenant.disabled_at else None,
            },
        )
    set_llm_tenant(str(tenant.id))
    # W2: RLS-Kontext auf DB-Session setzen — Postgres erzwingt Tenant-Isolation
    # für alle folgenden Queries (auch Raw-SQL) auf dieser Session.
    await set_rls_tenant(db, str(tenant.id))
    return tenant


async def get_tenant_id(
    x_api_key: str = Header(...), db: AsyncSession = Depends(get_db)
) -> uuid.UUID:
    result = await db.execute(
        select(Tenant).where(
            (Tenant.api_key == x_api_key) | (Tenant.api_key_secondary == x_api_key)
        )
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not tenant.enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "tenant_disabled",
                "reason": tenant.disabled_reason or "Tenant ist deaktiviert",
                "since": tenant.disabled_at.isoformat() if tenant.disabled_at else None,
            },
        )
    set_llm_tenant(str(tenant.id))
    await set_rls_tenant(db, str(tenant.id))  # W2: RLS-Kontext (siehe get_tenant)
    return tenant.id
