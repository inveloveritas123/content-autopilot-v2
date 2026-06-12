"""
tasks/canonical_wiring.py — DB-nahe Helfer für den nativen kanonischen Schreibpfad.

Trennt die DB-/Zeit-Abhängigkeiten (sync_session_factory, datetime) vom
dep-freien Kern in services/schema_transformer.py, damit dieser via importlib
testbar bleibt (services/__init__.py zieht google.generativeai).

Verwendung in P01/P03/P04 (SOLL-IST-2026-06-12-wiring.md §6, Schritt 1):
    from tasks.canonical_wiring import fetch_tenant_meta, now_iso
    from services.schema_transformer import build_canonical_meta, finalize_canonical
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import text

from models.base import sync_session_factory

logger = logging.getLogger(__name__)


def now_iso() -> str:
    """Aktueller UTC-Zeitstempel als ISO-8601-String (für _meta.generated_at)."""
    return datetime.now(timezone.utc).isoformat()


def fetch_tenant_meta(tenant_id: str) -> Tuple[Optional[str], Optional[str]]:
    """Holt (tenant_name, agentur_id) für die _meta-Rehydration. Best-Effort.

    - tenant_name → schönerer kunde_id-Slug (z.B. 'eric-spielhaus').
    - agentur_id ← tenants.settings['agentur_id'] (Default 'zb' setzt der Builder).

    Wirft nie — bei jedem Fehler (None, None), der Builder fällt dann auf
    Slug(tenant_id) bzw. 'zb' zurück.
    """
    try:
        with sync_session_factory() as session:
            row = session.execute(
                text("SELECT name, settings FROM tenants WHERE id = :id"),
                {"id": tenant_id},
            ).fetchone()
        if row:
            name = row[0]
            settings = row[1] if isinstance(row[1], dict) else {}
            agentur_id = (settings or {}).get("agentur_id")
            return name, agentur_id
    except Exception as exc:  # pragma: no cover - defensiver Fallback
        logger.debug("fetch_tenant_meta(%s) fehlgeschlagen (fail-open): %s", tenant_id, exc)
    return None, None
