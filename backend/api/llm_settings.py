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

# Derive stable encryption key from tenant key (survives restarts)
import base64
import hashlib
from config import settings as _app_settings
_key_material = hashlib.sha256((_app_settings.default_tenant_key + "-llm-encrypt").encode()).digest()
_FERNET_KEY = base64.urlsafe_b64encode(_key_material)
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
    cost_limit_daily_cents: Optional[int] = None
    config: Optional[dict] = None


class ProviderUpdate(BaseModel):
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    task_assignment: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    cost_limit_daily_cents: Optional[int] = None
    config: Optional[dict] = None


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
            "config": p.config or {},
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
        cost_limit_daily_cents=data.cost_limit_daily_cents if data.cost_limit_daily_cents is not None else 500,
        config=data.config or {},
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
    if data.cost_limit_daily_cents is not None:
        provider.cost_limit_daily_cents = max(0, data.cost_limit_daily_cents)
    if data.config is not None:
        existing = provider.config or {}
        existing.update(data.config)
        provider.config = existing

    await db.commit()
    return {"updated": True}


@router.get("/llm-cost-history")
async def cost_history(
    days: int = 7,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get LLM cost history for the last N days."""
    from datetime import timedelta
    from models.llm_call_log import LLMCallLog
    from sqlalchemy import func as sqlfunc

    since = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(
            sqlfunc.date(LLMCallLog.created_at).label("date"),
            sqlfunc.sum(LLMCallLog.cost_cents).label("total_cents"),
            sqlfunc.count(LLMCallLog.id).label("calls"),
            sqlfunc.sum(LLMCallLog.prompt_tokens).label("input_tokens"),
            sqlfunc.sum(LLMCallLog.completion_tokens).label("output_tokens"),
        ).where(
            LLMCallLog.tenant_id == tenant.id,
            LLMCallLog.created_at >= since,
        ).group_by(sqlfunc.date(LLMCallLog.created_at)).order_by(sqlfunc.date(LLMCallLog.created_at))
    )
    rows = result.all()
    return [
        {
            "date": str(r.date),
            "total_cents": round(float(r.total_cents or 0), 2),
            "calls": r.calls,
            "input_tokens": r.input_tokens or 0,
            "output_tokens": r.output_tokens or 0,
        }
        for r in rows
    ]


@router.post("/llm-providers/{provider_id}/reset-cost")
async def reset_provider_cost(
    provider_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Reset today's cost counter for a provider (for testing / manual override)."""
    from sqlalchemy import text

    provider = await db.get(LLMProvider, uuid.UUID(provider_id))
    if not provider or provider.tenant_id != tenant.id:
        raise HTTPException(404, "Provider not found")

    provider.cost_spent_today_cents = 0
    provider.cost_reset_at = datetime.utcnow()

    # Also delete today's row from daily_cost_tenant for this tenant
    today = datetime.utcnow().date()
    await db.execute(
        text("DELETE FROM daily_cost_tenant WHERE tenant_id = :tid AND date = :d"),
        {"tid": str(tenant.id), "d": today},
    )

    await db.commit()
    return {"reset": True, "reset_at": provider.cost_reset_at.isoformat()}


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
                    "model": provider.model_name or "vertex/gemini-2.5-flash-lite@europe-central2",
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

    except httpx.HTTPStatusError as e:
        provider.last_test_at = datetime.utcnow()
        provider.last_test_status = "error"
        try:
            body = e.response.json()
            body_msg = body.get("error", {}).get("message") or body.get("message") or body.get("detail") or ""
        except Exception:
            body_msg = e.response.text[:200] if e.response.text else ""
        if e.response.status_code in (403, 412) and ("spend" in body_msg.lower() or "budget" in body_msg.lower() or "limit" in body_msg.lower()):
            msg = f"🔴 Budget/Spend-Limit erreicht ({e.response.status_code}) — Bitte Guthaben beim Provider aufladen. Details: {body_msg[:120]}"
        elif e.response.status_code == 412:
            msg = "🔴 Portal-Budget erschöpft (412) — Bitte Guthaben bei requesty.ai aufladen."
        elif e.response.status_code in (401, 403):
            detail = f" ({body_msg[:80]})" if body_msg else ""
            msg = f"🔴 Zugriff verweigert ({e.response.status_code}){detail} — API-Key prüfen oder Guthaben aufladen."
        elif e.response.status_code == 429:
            msg = "🟡 Rate-Limit erreicht (429) — kurz warten und nochmal versuchen."
        else:
            detail = f" — {body_msg[:100]}" if body_msg else ""
            msg = f"HTTP {e.response.status_code}{detail}"
        provider.last_test_error = msg
        await db.commit()
        return {"status": "error", "error": msg, "http_status": e.response.status_code}
    except Exception as e:
        provider.last_test_at = datetime.utcnow()
        provider.last_test_status = "error"
        provider.last_test_error = str(e)[:500]
        await db.commit()
        return {"status": "error", "error": str(e)[:200]}


class BenchmarkRequest(BaseModel):
    step: str  # analysis | ideation | post_generation | smart_questions
    item_id: Optional[str] = None  # specific item, or pick most recent


@router.post("/benchmark")
async def run_benchmark(
    data: BenchmarkRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Run a single LLM pipeline step and return quality + cost metrics.

    Runs the step without saving results to DB — read-only benchmark.
    Budget will be consumed for the one LLM call.
    """
    import time
    from sqlalchemy import select as sa_select, desc
    from models.source_item import SourceItem

    VALID_STEPS = {"analysis", "ideation", "post_generation", "smart_questions"}
    if data.step not in VALID_STEPS:
        raise HTTPException(400, f"Invalid step. Must be one of: {', '.join(VALID_STEPS)}")

    # Pick item
    if data.item_id:
        item = await db.get(SourceItem, uuid.UUID(data.item_id))
        if not item or item.tenant_id != tenant.id:
            raise HTTPException(404, "Item not found")
    else:
        # Pick most recent item that has the data needed for this step
        if data.step == "analysis":
            # Need transcript_text
            result = await db.execute(
                sa_select(SourceItem).where(
                    SourceItem.tenant_id == tenant.id,
                    SourceItem.transcript_text.isnot(None),
                ).order_by(desc(SourceItem.updated_at)).limit(1)
            )
        else:
            # Need analysis (content_ready or analyzed)
            result = await db.execute(
                sa_select(SourceItem).where(
                    SourceItem.tenant_id == tenant.id,
                    SourceItem.analysis.isnot(None),
                    SourceItem.transcript_text.isnot(None),
                ).order_by(desc(SourceItem.updated_at)).limit(1)
            )
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(404, "No suitable items found for benchmark")

    item_title = item.title or "(kein Titel)"

    # Check circuit breaker before attempting LLM call
    try:
        import redis as redis_lib, os
        _r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis-v2:6379/1"))
        if _r.get("llm:budget_exceeded"):
            ttl = _r.ttl("llm:budget_exceeded")
            return {
                "step": data.step,
                "item_id": str(item.id),
                "item_title": item.title[:80] if item.title else "—",
                "model_used": None,
                "latency_ms": 0,
                "quality_score": None,
                "result_preview": None,
                "error": f"LLM-Budget erschöpft (Pause noch ~{ttl}s). Bitte Guthaben bei requesty.ai aufladen, dann 'Pipeline fortsetzen' klicken.",
                "status": "budget_exceeded",
            }
    except Exception:
        pass

    t_start = time.time()
    result_preview = None
    quality_score = None
    error = None
    model_used = None

    try:
        if data.step == "analysis":
            from services.analyzer import analyze_transcript
            from services.llm import REQUESTY_MODELS, PURPOSE_MODEL_MAP
            analysis = await analyze_transcript(
                item.transcript_text,
                source_type="youtube",
                title=item.title or "",
            )
            model_used = REQUESTY_MODELS.get(PURPOSE_MODEL_MAP.get("analysis", "gemini-flash"), "gemini-flash")
            if analysis:
                from services.quality_scorer import score_analysis
                scores = score_analysis(analysis)
                quality_score = scores.get("overall_score")
                # Preview: key fields summary
                result_preview = (
                    f"Titel: {analysis.get('topic_title', '—')}\n"
                    f"Summary: {str(analysis.get('summary', ''))[:200]}\n"
                    f"Key Points: {len(analysis.get('key_points', []))} Punkte\n"
                    f"Tags: {', '.join(analysis.get('tags', [])[:5])}"
                )
            else:
                error = "Keine Analyse zurückgegeben"

        elif data.step == "ideation":
            from services.content_ideation import run_ideation_pipeline
            from services.llm import REQUESTY_MODELS, PURPOSE_MODEL_MAP
            ideas = await run_ideation_pipeline(
                analysis=item.analysis,
                title=item.title or "",
                transcript_excerpt=(item.transcript_text or "")[:500],
            )
            model_used = REQUESTY_MODELS.get(PURPOSE_MODEL_MAP.get("ideation", "claude-sonnet"), "claude-sonnet")
            if ideas:
                from services.quality_scorer import score_ideation
                idea_list = [{"angle": i.get("angle", ""), "title": i.get("title", "")} for i in ideas]
                scores = score_ideation(idea_list)
                quality_score = scores.get("overall_score")
                result_preview = "\n".join([
                    f"• {i.get('title', '—')} [{i.get('angle', '—')}]"
                    for i in ideas[:5]
                ])
            else:
                error = "Keine Ideen generiert"

        elif data.step == "smart_questions":
            from services.smart_questions import generate_smart_questions
            from services.llm import REQUESTY_MODELS, PURPOSE_MODEL_MAP
            entrepreneur = (tenant.settings or {}).get("entrepreneur", {})
            questions = await generate_smart_questions(
                item_id=str(item.id),
                transcript_text=item.transcript_text or "",
                analysis=item.analysis,
                title=item.title or "",
                entrepreneur=entrepreneur,
            )
            model_used = REQUESTY_MODELS.get(PURPOSE_MODEL_MAP.get("questions", "claude-sonnet"), "claude-sonnet")
            if questions:
                from services.quality_scorer import score_smart_questions
                scores = score_smart_questions(questions)
                quality_score = scores.get("overall_score")
                result_preview = "\n".join([
                    f"• {q.get('question_text', '—')[:100]}"
                    for q in questions[:4]
                ])
            else:
                error = "Keine Fragen generiert"

        elif data.step == "post_generation":
            from services.content_generator import generate_all_content
            from services.llm import REQUESTY_MODELS, PURPOSE_MODEL_MAP
            # Voice profile from tenant settings
            voice_profile = (tenant.settings or {}).get("voice_profile")
            if not voice_profile:
                voice_profile = {
                    "name": tenant.name or "Unternehmer",
                    "tone": "authentisch",
                    "industry": "Mittelstand",
                }
            content_dict = await generate_all_content(
                analysis=item.analysis,
                title=item.title or "",
                transcript_text=item.transcript_text or "",
                voice_profile=voice_profile,
            )
            model_used = REQUESTY_MODELS.get(PURPOSE_MODEL_MAP.get("post_generation", "claude-sonnet"), "claude-sonnet")
            linkedin_post = content_dict.get("linkedin") or ""
            if linkedin_post:
                from services.quality_scorer import score_post_generation
                scores = score_post_generation(linkedin_post)
                quality_score = scores.get("overall_score")
                result_preview = linkedin_post[:400] + ("..." if len(linkedin_post) > 400 else "")
            else:
                error = "Kein Post generiert"

    except Exception as e:
        error = str(e)[:300]

    latency_ms = int((time.time() - t_start) * 1000)

    return {
        "step": data.step,
        "item_id": str(item.id),
        "item_title": item_title[:80],
        "model_used": model_used,
        "latency_ms": latency_ms,
        "quality_score": quality_score,
        "result_preview": result_preview,
        "error": error,
        "status": "error" if error else "ok",
    }


class VoiceCompareRequest(BaseModel):
    item_id: Optional[str] = None  # specific item, or pick most recent content_ready


@router.post("/voice-compare")
async def run_voice_compare(
    data: VoiceCompareRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Run post_generation with all configured voice profiles for comparison.

    Reads all tenants with configured voice_profiles, generates posts from the same item
    concurrently using each profile, returns side-by-side results.
    """
    import asyncio as _asyncio
    import time
    from sqlalchemy import select as sa_select, desc
    from models.source_item import SourceItem
    from models.tenant import Tenant as TenantModel

    # Check budget
    try:
        import redis as redis_lib, os
        _r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis-v2:6379/1"))
        if _r.get("llm:budget_exceeded"):
            ttl = _r.ttl("llm:budget_exceeded")
            return {
                "status": "budget_exceeded",
                "error": f"LLM-Budget erschöpft (Pause noch ~{ttl}s). Budget aufladen und 'Pipeline fortsetzen' klicken.",
                "results": [],
            }
    except Exception:
        pass

    # Get all tenants with voice profiles
    all_tenants_result = await db.execute(sa_select(TenantModel).order_by(TenantModel.created_at))
    all_tenants = all_tenants_result.scalars().all()

    configured_tenants = [
        t for t in all_tenants
        if (t.settings or {}).get("voice_profile", {}).get("tone")
    ]

    if not configured_tenants:
        return {"status": "error", "error": "Keine Voice-Profile konfiguriert", "results": []}

    # Find source item (use current tenant's items, or specific item)
    source_item = None
    if data.item_id:
        source_item = await db.get(SourceItem, __import__('uuid').UUID(data.item_id))
    else:
        item_result = await db.execute(
            sa_select(SourceItem).where(
                SourceItem.tenant_id == tenant.id,
                SourceItem.analysis.isnot(None),
                SourceItem.transcript_text.isnot(None),
            ).order_by(desc(SourceItem.updated_at)).limit(1)
        )
        source_item = item_result.scalar_one_or_none()

    if not source_item:
        return {"status": "error", "error": "Kein geeignetes Item gefunden (kein analysiertes Item vorhanden)", "results": []}

    from services.content_generator import generate_all_content
    from services.llm import REQUESTY_MODELS, PURPOSE_MODEL_MAP
    from services.quality_scorer import score_post_generation

    async def generate_for_profile(t):
        voice_profile = (t.settings or {}).get("voice_profile", {})
        entrepreneur = (t.settings or {}).get("entrepreneur", {})
        t_start = time.time()
        try:
            content_dict = await generate_all_content(
                analysis=source_item.analysis,
                title=source_item.title or "",
                transcript_text=source_item.transcript_text or "",
                voice_profile=voice_profile,
            )
            linkedin_post = content_dict.get("linkedin") or ""
            latency_ms = int((time.time() - t_start) * 1000)
            quality_score = score_post_generation(linkedin_post).get("overall_score") if linkedin_post else None
            return {
                "tenant_name": t.name,
                "industry": entrepreneur.get("industry", "—"),
                "entrepreneur_name": entrepreneur.get("name", "—"),
                "tone": voice_profile.get("tone", "—"),
                "model_used": REQUESTY_MODELS.get(PURPOSE_MODEL_MAP.get("post_generation", "claude-sonnet"), "—"),
                "latency_ms": latency_ms,
                "quality_score": quality_score,
                "post_text": linkedin_post,
                "status": "ok" if linkedin_post else "empty",
            }
        except Exception as e:
            return {
                "tenant_name": t.name,
                "industry": (t.settings or {}).get("entrepreneur", {}).get("industry", "—"),
                "entrepreneur_name": (t.settings or {}).get("entrepreneur", {}).get("name", "—"),
                "tone": (t.settings or {}).get("voice_profile", {}).get("tone", "—"),
                "error": str(e)[:200],
                "status": "error",
            }

    # Run all profiles concurrently
    results = await _asyncio.gather(*[generate_for_profile(t) for t in configured_tenants[:3]])

    return {
        "status": "ok",
        "item_title": source_item.title[:80] if source_item.title else "—",
        "results": list(results),
    }
