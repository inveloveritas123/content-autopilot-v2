"""Bulkhead — Ressourcen-Kammern pro Tenant (W5, 2026-07-21).

Problem (Noisy-Neighbor): Alle Tenants teilen sich denselben Celery-Worker-Pool.
Lädt EIN Tenant 50 Transkripte auf einmal hoch, belegen seine 50 Jobs alle Worker
— die anderen Tenants warten. Ein Kunde ruiniert das Erlebnis für alle.

Lösung: Jeder Tenant bekommt ein Kontingent gleichzeitiger schwerer Tasks
(_MAX_CONCURRENT_PER_TENANT). Wird es überschritten, wird der Task zurückgestellt
(BulkheadFull) statt einen Worker-Slot zu belegen — die anderen Tenants bleiben
bedienbar. Wie ein Schiffsrumpf mit wasserdichten Kammern: ein Leck flutet nur eine.

Umsetzung: Postgres Advisory-Locks + ein Zähler in `tenant_concurrency`. Kein Redis
nötig (dependency-frei, deploybar). SET-basiert atomar via INSERT ... ON CONFLICT.

Dieses Modul stellt KEINE eigene Session — der Aufrufer übergibt seine (sync) Session
(die Tasks haben ohnehin eine). Das hält den Bulkhead transaktions-transparent.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Max. gleichzeitige schwere Tasks pro Tenant. Konservativ: ein Tenant kann seine
# Pipeline füllen, aber nicht den ganzen Pool. Via ENV überschreibbar.
_DEFAULT_MAX_CONCURRENT = 3


class BulkheadFull(Exception):
    """Der Tenant hat sein Kontingent gleichzeitiger Tasks erreicht."""


def _max_concurrent() -> int:
    import os

    try:
        return max(1, int(os.environ.get("BULKHEAD_MAX_CONCURRENT_PER_TENANT", "")))
    except (ValueError, TypeError):
        return _DEFAULT_MAX_CONCURRENT


def _acquire(session, tenant_id: str) -> bool:
    """Erhöht den Concurrency-Zähler atomar, wenn unter dem Limit. True bei Erfolg."""
    limit = _max_concurrent()
    row = session.execute(
        text(
            "INSERT INTO tenant_concurrency (tenant_id, active) "
            "VALUES (CAST(:tid AS uuid), 1) "
            "ON CONFLICT (tenant_id) DO UPDATE "
            "  SET active = tenant_concurrency.active + 1 "
            "  WHERE tenant_concurrency.active < :lim "
            "RETURNING active"
        ),
        {"tid": tenant_id, "lim": limit},
    ).first()
    session.commit()
    return row is not None


def _release(session, tenant_id: str) -> None:
    """Verringert den Concurrency-Zähler (nie unter 0)."""
    session.execute(
        text(
            "UPDATE tenant_concurrency SET active = GREATEST(active - 1, 0) "
            "WHERE tenant_id = CAST(:tid AS uuid)"
        ),
        {"tid": tenant_id},
    )
    session.commit()


@contextmanager
def tenant_slot(session, tenant_id: str):
    """Belegt einen Bulkhead-Slot für den Tenant; gibt ihn am Ende frei.

    Wirft BulkheadFull, wenn der Tenant sein Kontingent erreicht hat — der Aufrufer
    (Task) soll dann zurückstellen (Celery-Retry mit Backoff), NICHT den Slot belegen.
    """
    acquired = _acquire(session, tenant_id)
    if not acquired:
        raise BulkheadFull(
            f"Tenant {tenant_id} hat das Concurrency-Limit ({_max_concurrent()}) erreicht"
        )
    try:
        yield
    finally:
        try:
            _release(session, tenant_id)
        except Exception as exc:  # Freigabe darf nie den Task-Erfolg überschreiben
            logger.error("bulkhead: release für tenant %s fehlgeschlagen: %s", tenant_id, exc)
