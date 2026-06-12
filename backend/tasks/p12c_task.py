"""P12c-Task — LLM-basierter Carousel-Generator.

Workflow:
1. Kill-switch prüfen
2. Cost-Cap prüfen
3. Prompt laden (P12c_carousel, lokaler Fallback)
4. Anthropic-Call (Sonnet)
5. JSON-Parsing + Schema-Validierung
6. PDF-Generierung via carousel_generator
7. carousel_pdf_path in content_pieces speichern (optional)
8. Return dict: {slides, pdf_bytes (base64), slide_count}
"""

"""
Umgestellt: 2026-06-11 (P5-anthropic-provider.md)
  - anthropic-SDK-Bypass entfernt (ANTHROPIC_MODEL_ID / ANTHROPIC_PRICING_KEY entfernt)
  - BACKTEST_MODEL_OVERRIDE ersetzt durch MODEL_TIER_P12C Env-Variable
  - LLM-Call über call_pipeline_llm (Seam → Router)
  - Kosten-Schätzung über estimate_tier_cost statt estimate_anthropic_cost
"""
import base64
import hashlib
import json
import logging
import os
import time
import uuid
from datetime import UTC

from sqlalchemy import text

from models.base import sync_session_factory
from services.cost_cap import (
    CostCapExceeded,
    CostCapMiddleware,
)
from services.pipeline_llm import (
    BudgetExceededError,
    call_pipeline_llm,
    estimate_tier_cost,
    resolve_tier,
)
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Local fallback prompt (used if PromptLoader/NC unavailable)
_FALLBACK_SYSTEM = """Du bist ein LinkedIn-Content-Stratege. Wandle den Post in 5-7 Slides um.
Antworte NUR mit JSON: {"slides": [{"type": "cover"|"point"|"quote"|"cta", "title": "...", "body": "..."}], "slide_count": N}"""

_FALLBACK_USER_TEMPLATE = (
    """Post:\n---\n{post_text}\n---\nErstelle {slide_count} Slides. Voice-Hint: {voice_hint}"""
)

MAX_SLIDES = 8
MIN_SLIDES = 5


def _load_prompt():
    """Load P12c prompt from NC via PromptLoader, fallback to local file, then hardcoded."""
    try:
        from services.prompt_loader import get_default_prompt_loader

        loader = get_default_prompt_loader()
        return loader.load("P12c")
    except Exception as e:
        logger.warning(f"[P12c] PromptLoader fehlgeschlagen, nutze lokalen Fallback: {e}")

    # Try local file
    local_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "prompts", "P12c_carousel.md")
    )
    if os.path.exists(local_path):
        try:
            with open(local_path, encoding="utf-8") as f:
                content = f.read()
            from datetime import datetime

            from services.prompt_loader import LoadedPrompt, _extract_section

            sha = hashlib.sha256(content.encode()).hexdigest()
            return LoadedPrompt(
                content=content,
                system_prompt=_extract_section(content, "System-Prompt"),
                user_prompt_template=_extract_section(content, "User-Prompt"),
                sha=sha,
                loaded_at=datetime.now(UTC),
                source_path=local_path,
            )
        except Exception as le:
            logger.warning(f"[P12c] Lokaler Fallback fehlgeschlagen: {le}")

    # Hardcoded fallback
    from datetime import datetime

    from services.prompt_loader import LoadedPrompt

    fallback_content = (
        f"## System-Prompt\n{_FALLBACK_SYSTEM}\n\n## User-Prompt\n{_FALLBACK_USER_TEMPLATE}"
    )
    return LoadedPrompt(
        content=fallback_content,
        system_prompt=_FALLBACK_SYSTEM,
        user_prompt_template=_FALLBACK_USER_TEMPLATE,
        sha="fallback",
        loaded_at=datetime.now(UTC),
        source_path="hardcoded",
    )


def _parse_slides(raw: str) -> list[dict]:
    """Parse LLM output into slides list."""
    import html

    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
        slides = data.get("slides", [])
    except Exception:
        logger.warning("[P12c] JSON-Parse fehlgeschlagen, erstelle Fallback-Slides")
        slides = [
            {"type": "cover", "title": "Carousel", "body": raw[:200]},
        ]

    # Enforce max slides
    if len(slides) > MAX_SLIDES:
        slides = slides[:MAX_SLIDES]

    # Map P12c types → carousel_generator types
    TYPE_MAP = {
        "cover": "title",  # P12c "cover" → generator "title" (full-color slide)
        "point": "content",  # P12c "point" → generator "content" (content slide)
        "transition": "content",
        "quote": "quote",
        "cta": "cta",
        "title": "title",
        "content": "content",
    }
    clean = []
    for s in slides:
        raw_type = s.get("type", "point")
        slide_type = TYPE_MAP.get(raw_type, "content")
        clean.append(
            {
                "type": slide_type,
                "title": html.escape(str(s.get("title", s.get("heading", "")))),
                "body": html.escape(str(s.get("body", ""))),
                "heading": html.escape(
                    str(s.get("title", s.get("heading", "")))
                ),  # alias for generator
            }
        )
    return clean


@celery_app.task(name="tasks.p12c_task.run_p12c", bind=True, max_retries=1)
def run_p12c(
    self,
    tenant_id: str,
    post_text: str,
    voice_hint: str = "",
    content_piece_id: str | None = None,
    brand_colors: dict | None = None,
    slide_count: int = 6,
) -> dict:
    """P12c: Generate carousel slides + PDF from a LinkedIn post text.

    Returns:
        {status, slides, pdf_b64, slide_count, carousel_pdf_path or None}
    """
    from services.kill_switch import KillSwitchTriggered, check_kill_switch

    try:
        check_kill_switch(tenant_id)
    except KillSwitchTriggered:
        return {"status": "aborted", "reason": "tenant_disabled"}

    run_id = str(uuid.uuid4())
    t_start = time.time()

    # Cost-cap check (#123 Lücke: P12c-cap-call hatte falschen Methodennamen + fehlende DB-Session)
    _tier, _ = resolve_tier("P12C")
    est_cost = estimate_tier_cost(_tier, 4000, 1500)
    logger.info("P12c estimated cost=%.6f USD for tenant=%s", est_cost, tenant_id)
    try:
        import asyncio as _asyncio

        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker as _sm

        from config import settings as _s

        async def _p12c_cap_check():
            _engine = create_async_engine(_s.database_url, pool_pre_ping=True)
            _Session = _sm(_engine, class_=AsyncSession, expire_on_commit=False)
            try:
                async with _Session() as _sess:
                    await CostCapMiddleware(_sess).check_and_record(tenant_id, est_cost)
            finally:
                await _engine.dispose()

        _asyncio.run(_p12c_cap_check())
    except CostCapExceeded:
        logger.warning(
            "P12c run_id=%s tenant=%s: daily cost cap exceeded, abort", run_id, tenant_id
        )
        return {"status": "paused_for_cost", "reason": "daily_cost_cap_exceeded"}
    except Exception as cap_err:
        logger.warning("P12c cost-cap check failed (fail-open): %s", cap_err)

    # Load tenant branding for brand_colors if not provided
    if brand_colors is None:
        try:
            with sync_session_factory() as session:
                row = session.execute(
                    text(
                        "SELECT primary_color, secondary_color FROM tenant_branding WHERE tenant_id = :tid"
                    ),
                    {"tid": tenant_id},
                ).fetchone()
                if row:
                    brand_colors = {"primary": row[0], "accent": row[1]}
        except Exception as be:
            logger.warning(f"[P12c] Branding-Load fehlgeschlagen: {be}")

    # Load prompt
    slide_count = max(MIN_SLIDES, min(MAX_SLIDES, slide_count))
    prompt = _load_prompt()

    user_content = prompt.user_prompt_template.format(
        post_text=post_text[:3000],
        slide_count=slide_count,
        voice_hint=(voice_hint or "professionell, persönlich")[:500],
    )

    # LLM-Call über den Seam (kein direkter SDK-Aufruf)
    # BACKTEST_MODEL_OVERRIDE wird durch MODEL_TIER_P12C Env-Variable ersetzt
    try:
        res = call_pipeline_llm(
            prompt_key="P12C",
            system_prompt=prompt.system_prompt,
            user_content=user_content,
            tenant_id=tenant_id,
        )
        raw_output = res.text.strip()
    except BudgetExceededError:
        # BUG-1-Fix: Router-Budget überschritten (HTTP 412) → paused_for_cost, kein Retry
        logger.warning(
            "[P12c] run_id=%s tenant=%s: Router-Budget überschritten (412), pausing",
            run_id,
            tenant_id,
        )
        return {"run_id": run_id, "status": "paused_for_cost"}
    except Exception as api_err:
        logger.error(f"[P12c] LLM-Call fehlgeschlagen: {api_err}")
        return {"status": "failed", "error": str(api_err)}

    # Parse slides
    slides = _parse_slides(raw_output)
    if not slides:
        return {"status": "failed", "error": "Keine gültigen Slides generiert"}

    # Generate PDF
    try:
        from services.carousel_generator import generate_carousel_pdf

        pdf_bytes = generate_carousel_pdf(
            slides=slides,
            brand_colors=brand_colors,
            title="LinkedIn Carousel",
        )
        # Enforce LinkedIn 5 MB limit
        if len(pdf_bytes) > 5 * 1024 * 1024:
            logger.warning(
                f"[P12c] PDF zu gross ({len(pdf_bytes)} bytes > 5MB), wird nicht gespeichert"
            )
            pdf_bytes = None
            pdf_b64 = None
        else:
            pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    except Exception as pdf_err:
        logger.error(f"[P12c] PDF-Generierung fehlgeschlagen: {pdf_err}")
        pdf_b64 = None
        pdf_bytes = None

    # Store carousel_pdf_path in content_piece if provided
    carousel_pdf_path = None
    if content_piece_id and pdf_bytes:
        try:
            carousel_pdf_path = f"carousel/{tenant_id}/{content_piece_id}/{run_id}.pdf"
            with sync_session_factory() as session:
                session.execute(
                    text(
                        "UPDATE content_pieces SET carousel_pdf_path = :path WHERE id = :id AND tenant_id = :tid"
                    ),
                    {"path": carousel_pdf_path, "id": content_piece_id, "tid": tenant_id},
                )
                session.commit()
        except Exception as db_err:
            logger.warning(f"[P12c] carousel_pdf_path-Update fehlgeschlagen: {db_err}")
            carousel_pdf_path = None

    elapsed = time.time() - t_start
    logger.info(f"[P12c] run_id={run_id} slides={len(slides)} elapsed={elapsed:.1f}s")

    result = {
        "status": "done",
        "run_id": run_id,
        "slides": slides,
        "slide_count": len(slides),
        "carousel_pdf_path": carousel_pdf_path,
    }
    if pdf_b64:
        result["pdf_b64"] = pdf_b64
    return result
