import asyncio
import json as _json
import logging

from sqlalchemy import select
from sqlalchemy import text as _text

from models.base import sync_session_factory
from models.campaign import Campaign
from models.content_piece import ContentPiece
from models.source import Source
from models.source_item import SourceItem
from models.tenant import Tenant
from services.analyzer import analyze_transcript
from services.campaign_matcher import match_item_to_campaigns
from services.content_generator import generate_all_content
from services.fact_checker import check_facts
from services.llm import BudgetExceededError, set_llm_tenant
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.generate_task.analyze_item")
def analyze_item(item_id: str):
    """Analyze a transcribed item — then auto-chain to ideation."""
    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item:
            logger.error(f"Item {item_id} not found")
            return

        # RSS items often have no full transcript — use title as minimal content
        if not item.transcript_text:
            if item.transcript_source == "rss_feed" and item.title:
                logger.info(
                    f"Item {item_id}: RSS item has no transcript, using title as content stub"
                )
                item.transcript_text = item.title
                session.commit()
            else:
                logger.error(f"Item {item_id} has no transcript and no title fallback")
                return

        item.status = "analyzing"
        session.commit()

        # Source-Typ ermitteln für kontextabhängige Analyse
        source = session.get(Source, item.source_id) if item.source_id else None
        source_type = source.type if source else "youtube"

        # Load tenant routing overrides (if any)
        tenant = session.get(Tenant, item.tenant_id)
        routing_override = (tenant.settings or {}).get("llm_routing") if tenant else None

        # Set tenant context so LLM cost tracking updates daily_cost_tenant
        set_llm_tenant(str(item.tenant_id))
        try:
            analysis = asyncio.run(
                analyze_transcript(
                    item.transcript_text,
                    source_type=source_type,
                    title=item.title or "",
                    routing_override=routing_override,
                )
            )

            if analysis:
                # Fact check top claims
                fact_results = asyncio.run(check_facts(analysis.get("key_points", [])))
                if fact_results:
                    analysis["fact_check"] = fact_results

                item.analysis = analysis
                item.status = "analyzed"

                # Campaign matching
                campaigns = (
                    session.execute(
                        select(Campaign).where(
                            Campaign.tenant_id == item.tenant_id,
                            Campaign.is_active.is_(True),
                        )
                    )
                    .scalars()
                    .all()
                )

                campaign_dicts = [
                    {"id": c.id, "keywords": c.keywords, "name": c.name} for c in campaigns
                ]
                match_id = match_item_to_campaigns(analysis, campaign_dicts)
                if match_id:
                    item.campaign_match_id = match_id

                # Auto-score analysis quality
                try:
                    from models.quality_metric import QualityMetric
                    from services.llm import PURPOSE_MODEL_MAP, REQUESTY_MODELS
                    from services.quality_scorer import score_analysis

                    scores = score_analysis(analysis)
                    model_key = PURPOSE_MODEL_MAP.get("analysis", "gemini-flash")
                    qm = QualityMetric(
                        source_item_id=item.id,
                        tenant_id=item.tenant_id,
                        step="analysis",
                        model_used=REQUESTY_MODELS.get(model_key, model_key),
                        completeness_score=scores.get("completeness_score"),
                        overall_score=scores.get("overall_score"),
                    )
                    session.add(qm)
                except Exception as qe:
                    logger.warning(f"Quality scoring failed for analysis {item_id}: {qe}")

                session.commit()
                logger.info(f"Item {item_id} analyzed successfully (source_type={source_type})")

                # ═══ AUTO-CHAIN: Content generieren (Quick-Mode) ═══
                generate_content.delay(item_id)

                # ═══ AUTO-CHAIN: Ideen + Fragen generieren (Dialog-Mode) ═══
                from tasks.ideation_task import auto_generate_ideas

                auto_generate_ideas.delay(item_id)

                # ═══ AUTO-CHAIN: Smarte Fragen für Dialogue-Workflow ═══
                from tasks.questions_task import generate_smart_questions_task

                generate_smart_questions_task.delay(item_id)

            else:
                item.status = "transcribed"  # Reset to allow retry
                session.commit()
                logger.warning(f"Analysis failed for {item_id}")

        except Exception as e:
            logger.error(f"Analysis failed for {item_id}: {e}")
            item.status = "transcribed"
            session.commit()
            # Circuit breaker: if budget exceeded, set a Redis flag to pause pipeline
            if "BudgetExceededError" in type(e).__name__ or "412" in str(e):
                try:
                    import os

                    import redis as redis_lib

                    r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis-v2:6379/1"))
                    r.set("llm:budget_exceeded", "1")  # persists until manual reset via dashboard
                    logger.warning(
                        "Budget exceeded — pipeline paused (llm:budget_exceeded set, no TTL — reset manually via dashboard)"
                    )
                except Exception:
                    pass

    # Return actual item status from DB (not hardcoded "analyzed")
    with sync_session_factory() as session:
        final_item = session.get(SourceItem, item_id)
        actual_status = final_item.status if final_item else "unknown"
    return {"item_id": item_id, "status": actual_status}


@celery_app.task(
    name="tasks.generate_task.generate_content", bind=True, max_retries=5, default_retry_delay=30
)
def generate_content(self, item_id: str):
    """Generate content for all channels from an analyzed item (Quick-Mode).

    W5-Bulkhead: begrenzt gleichzeitige Generierungen PRO Tenant — ein Kunde mit
    vielen Jobs blockiert nicht den ganzen Worker-Pool. Ist das Tenant-Kontingent
    voll, wird der Task zurückgestellt (Celery-Retry mit Backoff), statt einen
    Worker-Slot zu belegen.
    """
    from services.bulkhead import _acquire, _release
    from services.rls import set_rls_tenant_sync

    # tenant_id + Slot-Acquire in einer kurzen Session.
    with sync_session_factory() as _bh_session:
        item = _bh_session.get(SourceItem, item_id)
        if not item or not item.analysis:
            logger.error(f"Item {item_id} not found or not analyzed")
            return
        _bulk_tenant = str(item.tenant_id)
        set_rls_tenant_sync(_bh_session, _bulk_tenant)
        if not _acquire(_bh_session, _bulk_tenant):
            logger.info(
                "generate_content: Tenant %s Bulkhead voll — Task zurückgestellt", _bulk_tenant
            )
            raise self.retry(countdown=30)

    # Slot belegt → generieren, danach IMMER freigeben.
    try:
        _generate_content_inner(item_id)
    finally:
        try:
            with sync_session_factory() as _rel_session:
                set_rls_tenant_sync(_rel_session, _bulk_tenant)
                _release(_rel_session, _bulk_tenant)
        except Exception as _rel_exc:
            logger.error("generate_content: Bulkhead-Release fehlgeschlagen: %s", _rel_exc)


def _generate_content_inner(item_id: str):
    """Eigentliche Generierung (vom Bulkhead-Wrapper umschlossen)."""
    with sync_session_factory() as session:
        item = session.get(SourceItem, item_id)
        if not item or not item.analysis:
            logger.error(f"Item {item_id} not found or not analyzed")
            return

        item.status = "generating"
        session.commit()

        tenant = session.get(Tenant, item.tenant_id)
        tenant_settings = (tenant.settings or {}) if tenant else {}
        tone = tenant_settings.get("tone", "professionell, informativ, mit persoenliche Note")
        routing_override = tenant_settings.get("llm_routing")
        voice_profile = tenant_settings.get("voice_profile") or None

        # Prefer Wizard/P03 voice profile from tenant_voice_profile table
        try:
            vp_row = session.execute(
                _text(
                    "SELECT payload FROM tenant_voice_profile"
                    " WHERE tenant_id=:t AND is_active=true"
                    " ORDER BY version DESC LIMIT 1"
                ),
                {"t": str(item.tenant_id)},
            ).fetchone()
            if vp_row and vp_row[0]:
                wizard_profile = (
                    vp_row[0] if isinstance(vp_row[0], dict) else _json.loads(vp_row[0])
                )
                if wizard_profile:
                    voice_profile = wizard_profile
                    logger.info(f"Using Wizard voice profile for item {item_id}")
        except Exception as vp_err:
            logger.warning(f"Could not load tenant_voice_profile for {item_id}: {vp_err}")
            # Fall through to v1 settings already set above

        # Set tenant context for cost cap tracking
        set_llm_tenant(str(item.tenant_id))
        try:
            content = asyncio.run(
                generate_all_content(
                    analysis=item.analysis,
                    title=item.title or "",
                    transcript_text=item.transcript_text or "",
                    video_url=item.url or "",
                    tone=tone,
                    voice_profile=voice_profile,
                    routing_override=routing_override,
                )
            )

            pieces_added = 0
            for channel, text in content.items():
                if text:
                    piece = ContentPiece(
                        source_item_id=item.id,
                        tenant_id=item.tenant_id,
                        channel=channel,
                        content_text=text,
                        content_metadata={"source_title": item.title, "source_url": item.url},
                        status="draft",
                    )
                    session.add(piece)
                    pieces_added += 1

                    # Auto-score post quality (rule-based, no LLM cost)
                    try:
                        from models.quality_metric import QualityMetric
                        from services.llm import PURPOSE_MODEL_MAP, REQUESTY_MODELS
                        from services.quality_scorer import score_post_generation

                        scores = score_post_generation(text)
                        model_key = PURPOSE_MODEL_MAP.get("post_generation", "claude-sonnet")
                        qm = QualityMetric(
                            source_item_id=item.id,
                            tenant_id=item.tenant_id,
                            step="post_generation",
                            model_used=REQUESTY_MODELS.get(model_key, model_key),
                            completeness_score=scores.get("completeness_score"),
                            accuracy_score=scores.get("accuracy_score"),
                            overall_score=scores.get("overall_score"),
                        )
                        session.add(qm)
                    except Exception as qe:
                        logger.warning(f"Post quality scoring failed for {item_id}/{channel}: {qe}")

            item.status = "content_ready"
            session.commit()
            logger.info(f"Content generated for item {item_id}: {pieces_added} pieces")

        except BudgetExceededError as e:
            logger.error(f"Content generation failed for {item_id}: {e}")
            item.status = "analyzed"
            session.commit()
            try:
                import os

                import redis as redis_lib

                r = redis_lib.from_url(os.environ.get("REDIS_URL", "redis://redis-v2:6379/1"))
                r.set("llm:budget_exceeded", "1")  # persists until manual reset
                logger.warning(
                    "Budget exceeded in generate_content — pipeline paused for 20 minutes"
                )
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Content generation failed for {item_id}: {e}")
            item.status = "analyzed"
            session.commit()

    with sync_session_factory() as session:
        final_item = session.get(SourceItem, item_id)
        actual_status = final_item.status if final_item else "unknown"
    return {"item_id": item_id, "status": actual_status}
