"""Daily cost reset for LLM providers."""

import logging
from datetime import datetime

from sqlalchemy import update

from models.base import sync_session_factory
from models.llm_provider import LLMProvider
from services.rls import set_rls_bypass_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.cost_reset_task.reset_daily_costs")
def reset_daily_costs():
    """Reset cost_spent_today_cents for all providers at midnight."""
    with sync_session_factory() as session:
        # Cross-Tenant-Cron: setzt die Tageskosten ALLER Provider zurueck, ohne
        # tenant_id-Filter. llm_providers traegt seit Migration 058 FORCE ROW
        # LEVEL SECURITY — ohne Bypass trifft das UPDATE 0 Zeilen und laeuft
        # wirkungslos durch (rowcount 0, kein Fehler). Die Kostenzaehler wuerden
        # nie zurueckgesetzt und jeder Tenant liefe nach einem Tag dauerhaft in
        # sein Kostenlimit.
        set_rls_bypass_sync(session, True)
        result = session.execute(
            update(LLMProvider)
            .where(LLMProvider.cost_spent_today_cents > 0)
            .values(
                cost_spent_today_cents=0,
                cost_reset_at=datetime.utcnow(),
            )
        )
        session.commit()
        count = result.rowcount
        if count:
            logger.info(f"Reset daily costs for {count} providers")
        return {"reset": count}
