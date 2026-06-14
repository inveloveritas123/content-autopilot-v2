"""
services/model_mode.py — Per-Tenant Modell-Modus-Switch (Issue #72).

Drei Modi:
  'testmodus'        — Default. Bit-identisches AKTUELLES Routing (Gemini-Remap für kreative Pfade).
  'produktiv'        — Anthropic-Quality via EU-souveränem Bedrock-Frankfurt (S6).
  'benutzerdefiniert'— Platzhalter; verhält sich wie 'testmodus' bis per-purpose-Overrides kommen.

SICHERHEITS-INVARIANTE: Default = 'testmodus' → bei jedem Fehler/fehlenden Kontext
wird 'testmodus' zurückgegeben (fail-safe = aktuelles Verhalten, keine Überraschung).

Das Setup (P01/P03/P04/P12 via pipeline_llm, S6) ist NICHT betroffen — pipeline_llm.py
bleibt in jedem Modus unangetastet.

KEY-INVARIANTE (Opus-Review #72):
  _resolve_model gibt IMMER einen KEY aus REQUESTY_MODELS zurück, niemals einen
  aufgelösten Modell-String. Das hält _litellm bit-identisch für testmodus und
  ermöglicht korrektes task-Tracking + Bedrock-Routing für produktiv.
  - testmodus       → KEY "claude-sonnet"     (→ Gemini via REQUESTY_MODELS, unverändert)
  - produktiv       → KEY "claude-sonnet-eu"  (→ Bedrock Frankfurt via REQUESTY_MODELS)
  - benutzerdefiniert → None (kein Override, aktuelles Verhalten)
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Gültige Modus-Werte (Menge — schnelle Validierung) ──────────────────────
VALID_MODEL_MODES: frozenset[str] = frozenset({"testmodus", "produktiv", "benutzerdefiniert"})

# ── Default — MUSS 'testmodus' bleiben (Sicherheits-Invariante) ─────────────
DEFAULT_MODEL_MODE: str = "testmodus"

# ── KEY je Modus (NICHT aufgelöste Strings — KEY-Invariante) ─────────────────
# Rückgabewert ist immer ein Key aus REQUESTY_MODELS (oder None).
# _litellm löst den Key auf → task-Ableitung + Cost-Tracking bleiben korrekt.
#
# 'testmodus'         → "claude-sonnet"     — exakt derselbe Key wie bisher → bit-identisch
# 'produktiv'         → "claude-sonnet-eu"  — neuer Key → Bedrock-Frankfurt (S6, EU)
# 'benutzerdefiniert' → None               — kein Override → aktuelles Verhalten
CREATIVE_MODEL_BY_MODE: dict[str, str | None] = {
    "testmodus": "claude-sonnet",     # KEY — löst via REQUESTY_MODELS zu Gemini auf
    "produktiv": "claude-sonnet-eu",  # KEY — löst via REQUESTY_MODELS zu Bedrock-Frankfurt auf
    "benutzerdefiniert": None,         # kein Override → heutiges Verhalten
}

# ── Kreative Model-Keys (werden in _resolve_model abgefangen) ────────────────
# Alle Keys aus REQUESTY_MODELS die durch den Modus beeinflusst werden.
# "claude-sonnet-eu" ist der neue produktiv-Key; beide müssen hier stehen.
CREATIVE_MODEL_KEYS: frozenset[str] = frozenset({"claude-sonnet", "claude-sonnet-eu"})

# ── Kreative Purposes (werden in _resolve_model abgefangen) ──────────────────
# Exakt die Purposes aus PURPOSE_MODEL_MAP die auf "claude-sonnet" zeigen.
CREATIVE_PURPOSES: frozenset[str] = frozenset(
    {"ideation", "questions", "creative", "post_generation", "onboarding"}
)


def get_tenant_model_mode(tenant_id: str | None) -> str:
    """Liest den model_mode aus tenant.settings (JSONB).

    Fail-open: bei jedem Fehler (DB nicht erreichbar, Tenant nicht gefunden,
    ungültiger Wert) wird 'testmodus' zurückgegeben — Sicherheits-Invariante.

    WICHTIG: Diese Funktion macht einen synchronen DB-Zugriff (via sync_session_factory),
    analog zum Cap-Check in _litellm. Sie darf nur im LLM-Routing-Pfad aufgerufen
    werden, nicht auf dem Event-Loop direkt.
    """
    if not tenant_id:
        return DEFAULT_MODEL_MODE
    try:
        from sqlalchemy import text as _t

        from models.base import sync_session_factory

        with sync_session_factory() as session:
            row = session.execute(
                _t("SELECT settings FROM tenants WHERE id = :tid"),
                {"tid": tenant_id},
            ).fetchone()
        if row is None:
            return DEFAULT_MODEL_MODE
        settings: dict = row[0] or {}
        mode = settings.get("model_mode", DEFAULT_MODEL_MODE)
        if mode not in VALID_MODEL_MODES:
            logger.warning(
                "model_mode '%s' für tenant %s ungültig — Fallback 'testmodus'", mode, tenant_id
            )
            return DEFAULT_MODEL_MODE
        return mode
    except Exception as exc:
        logger.debug("get_tenant_model_mode fehlgeschlagen (fail-open → testmodus): %s", exc)
        return DEFAULT_MODEL_MODE


