"""Daily cost reset for LLM providers."""

import logging
from datetime import datetime

from sqlalchemy import update

from models.base import sync_session_factory
from models.llm_provider import LLMProvider
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.cost_reset_task.reset_daily_costs")
def reset_daily_costs():
    """Reset cost_spent_today_cents for all providers at midnight."""
    with sync_session_factory() as session:
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
