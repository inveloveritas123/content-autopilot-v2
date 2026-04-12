from fastapi import Header, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.base import async_session_factory
from models.tenant import Tenant


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


async def get_tenant(x_api_key: str = Header(...), db: AsyncSession = Depends(get_db)) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.api_key == x_api_key))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant
