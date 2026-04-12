"""LLM Provider Settings — CRUD + Test."""
import uuid
from datetime import datetime
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.llm_provider import LLMProvider

router = APIRouter(prefix="/settings", tags=["settings"])

# Simple encryption key derived from app — in production use env var
_FERNET_KEY = Fernet.generate_key()
_fernet = Fernet(_FERNET_KEY)


def _encrypt_key(key: str) -> str:
    return _fernet.encrypt(key.encode()).decode()


def _decrypt_key(encrypted: str) -> str:
    try:
        return _fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        return "***"


def _mask_key(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    decrypted = _decrypt_key(key)
    if len(decrypted) <= 8:
        return "***"
    return decrypted[:4] + "..." + decrypted[-4:]


# Schemas

class ProviderCreate(BaseModel):
    name: str
    provider_type: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    task_assignment: str = "all"
    is_default: bool = False


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    task_assignment: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


# Endpoints

@router.get("/llm-providers")
async def list_providers(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LLMProvider).where(LLMProvider.tenant_id == tenant.id).order_by(LLMProvider.created_at)
    )
    providers = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "provider_type": p.provider_type,
            "api_key_masked": _mask_key(p.api_key_encrypted),
            "base_url": p.base_url,
            "model_name": p.model_name,
            "task_assignment": p.task_assignment,
            "is_active": p.is_active,
            "is_default": p.is_default,
            "last_test_at": p.last_test_at.isoformat() if p.last_test_at else None,
            "last_test_status": p.last_test_status,
            "last_test_error": p.last_test_error,
            "cost_limit_daily_cents": p.cost_limit_daily_cents,
            "cost_spent_today_cents": p.cost_spent_today_cents,
            "cost_reset_at": p.cost_reset_at.isoformat() if p.cost_reset_at else None,
        }
        for p in providers
    ]


@router.post("/llm-providers")
async def create_provider(
    data: ProviderCreate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    provider = LLMProvider(
        tenant_id=tenant.id,
        name=data.name,
        provider_type=data.provider_type,
        api_key_encrypted=_encrypt_key(data.api_key) if data.api_key else None,
        base_url=data.base_url,
        model_name=data.model_name,
        task_assignment=data.task_assignment,
        is_default=data.is_default,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return {"id": str(provider.id), "name": provider.name}


@router.patch("/llm-providers/{provider_id}")
async def update_provider(
    provider_id: str,
    data: ProviderUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    provider = await db.get(LLMProvider, uuid.UUID(provider_id))
    if not provider or provider.tenant_id != tenant.id:
        raise HTTPException(404, "Provider not found")

    if data.name is not None:
        provider.name = data.name
    if data.api_key is not None:
        provider.api_key_encrypted = _encrypt_key(data.api_key)
    if data.base_url is not None:
        provider.base_url = data.base_url
    if data.model_name is not None:
        provider.model_name = data.model_name
    if data.task_assignment is not None:
        provider.task_assignment = data.task_assignment
    if data.is_active is not None:
        provider.is_active = data.is_active
    if data.is_default is not None:
        provider.is_default = data.is_default

    await db.commit()
    return {"updated": True}


@router.delete("/llm-providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    provider = await db.get(LLMProvider, uuid.UUID(provider_id))
    if not provider or provider.tenant_id != tenant.id:
        raise HTTPException(404, "Provider not found")
    await db.delete(provider)
    await db.commit()
    return {"deleted": True}


@router.post("/llm-providers/{provider_id}/test")
async def test_provider(
    provider_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Test a provider by sending a minimal request."""
    import httpx

    provider = await db.get(LLMProvider, uuid.UUID(provider_id))
    if not provider or provider.tenant_id != tenant.id:
        raise HTTPException(404, "Provider not found")

    api_key = _decrypt_key(provider.api_key_encrypted) if provider.api_key_encrypted else ""
    base_url = provider.base_url or "http://host.docker.internal:4000/v1"

    try:
        start = datetime.utcnow()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                json={
                    "model": provider.model_name or "google/gemini-2.0-flash",
                    "messages": [{"role": "user", "content": "Say hello in one word."}],
                    "max_tokens": 10,
                },
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            latency_ms = int((datetime.utcnow() - start).total_seconds() * 1000)

        provider.last_test_at = datetime.utcnow()
        provider.last_test_status = "ok"
        provider.last_test_error = None
        await db.commit()
        return {"status": "ok", "latency_ms": latency_ms}

    except Exception as e:
        provider.last_test_at = datetime.utcnow()
        provider.last_test_status = "error"
        provider.last_test_error = str(e)[:500]
        await db.commit()
        return {"status": "error", "error": str(e)[:200]}
