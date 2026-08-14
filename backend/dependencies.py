import uuid

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.base import async_session_factory
from models.tenant import Tenant
from models.user import User
from services import auth as auth_svc
from services.llm import set_llm_tenant
from services.rls import set_rls_tenant


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


async def _resolve_tenant_by_api_key(x_api_key: str, db: AsyncSession) -> Tenant:
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
    return tenant


async def _resolve_tenant(request: Request, x_api_key: str, db: AsyncSession) -> Tenant:
    """Löst den Tenant primär per Session-Cookie auf, sonst per API-Key.

    Nähte-Fund (Highlander-Integration, 2026-08-14): `get_tenant` prüfte bisher
    NUR den X-Api-Key-Header — der Session-Login (`get_current_user`,
    api/auth.py) schützt bislang ausschließlich seinen eigenen `/auth/me`-
    Endpunkt. Wer den API-Key kennt (z.B. aus dem Browser-localStorage
    ausgelesen), kommt auf jede Business-Route, auch ohne eingeloggt zu sein.

    Fix: Ist ein gültiges Session-Cookie vorhanden, wird der Tenant über den
    eingeloggten User aufgelöst (X-Api-Key wird dann nur noch zur
    Tenant-AUSWAHL genutzt, falls ein User mehrere Tenants verwaltet — Zugriff
    wird über `user_may_access_tenant` erzwungen, nicht mehr nur über Kenntnis
    des Keys). Fehlt das Cookie (z.B. externe API-Nutzer wie das
    Cowork/Bauleiter-Dashboard, README-COWORK-INTEGRATION.md), bleibt die
    reine Key-Prüfung bestehen — kein Breaking Change für bestehende
    API-Key-only-Consumer.
    """
    cookie = request.cookies.get(auth_svc.USER_COOKIE_NAME)
    user_id = auth_svc.verify_session(cookie) if cookie else None
    if user_id is None:
        return await _resolve_tenant_by_api_key(x_api_key, db)

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        return await _resolve_tenant_by_api_key(x_api_key, db)

    tenant = await _resolve_tenant_by_api_key(x_api_key, db)
    if not await auth_svc.user_may_access_tenant(db, user, str(tenant.id)):
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diesen Tenant")
    return tenant


async def get_tenant(
    request: Request, x_api_key: str = Header(...), db: AsyncSession = Depends(get_db)
) -> Tenant:
    tenant = await _resolve_tenant(request, x_api_key, db)
    set_llm_tenant(str(tenant.id))
    # W2: RLS-Kontext auf DB-Session setzen — Postgres erzwingt Tenant-Isolation
    # für alle folgenden Queries (auch Raw-SQL) auf dieser Session.
    await set_rls_tenant(db, str(tenant.id))
    return tenant


async def get_tenant_id(
    request: Request, x_api_key: str = Header(...), db: AsyncSession = Depends(get_db)
) -> uuid.UUID:
    tenant = await _resolve_tenant(request, x_api_key, db)
    set_llm_tenant(str(tenant.id))
    await set_rls_tenant(db, str(tenant.id))  # W2: RLS-Kontext (siehe get_tenant)
    return tenant.id
