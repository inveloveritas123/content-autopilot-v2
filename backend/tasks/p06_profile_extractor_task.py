"""P06 — Self-Learning Company-Profile-Extractor (Issue #148, Welle D).

Nightly: scannt memory_chunks (Voice-Transkripte etc.) → extrahiert
strukturierte Felder ins company_profile.

- Confidence ≥ 0.85 → auto-merge (nur wenn Feld leer ODER current Trust niedriger)
- Confidence < 0.85 → Provenance mit applied=false (Review-Queue)
- Konflikt-Resolution: höhere Trust-Quelle wird nicht überschrieben
- LLM-Call (Gemini Flash via Requesty) mit fester JSON-Antwort
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import Any

from sqlalchemy import select, text

from models.base import sync_session_factory
from models.company_profile import (
    AUTO_APPLY_THRESHOLD,
    SOURCE_TRUST,
    CompanyProfile,
    ProfileFieldProvenance,
)
from services.anweisungs_marker import SQL_OHNE_ANWEISUNGEN
from services.soft_delete_filter import SQL_NICHT_GELOESCHT
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Du bist ein Profil-Extractor für ein Linkedin-Content-Tool.
Extrahiere aus dem Text strukturierte Firmen-Profil-Felder, falls erkennbar.

Mögliche Felder:
- company_name (Firmenname)
- industry (Branche)
- contact_person_name (Name Geschäftsführer/Ansprechpartner)
- contact_role (Rolle/Position)
- website (URL)
- region (Stadt/Region)
- founded_year (4-stellige Jahreszahl)
- headcount (Mitarbeiterzahl als Integer)
- usp (Alleinstellung, max 200 Zeichen)
- target_audience (Zielgruppe, max 200 Zeichen)
- values_short (Werte kurz, max 200 Zeichen)

REGELN:
- Nur extrahieren wenn klar im Text erwähnt
- Keine Halluzinationen, keine Vermutungen
- Bei Kunden-Stories (z.B. "ein Kunde von uns hat 50 MA") NICHT extrahieren — nur eigene Firma
- confidence: 0.0–1.0 wie sicher du bist (≥0.85 = klare Selbst-Aussage)

ANTWORT als JSON:
{
  "extractions": [
    {"field": "company_name", "value": "ZKG", "confidence": 0.95, "evidence": "Zitat aus Text"}
  ]
}

Wenn nichts erkannt: {"extractions": []}
"""


def _truncate(s: str | None, max_chars: int) -> str | None:
    if s is None:
        return None
    s = s.strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


@celery_app.task(name="tasks.p06_profile_extractor_task.run_for_tenant")
def run_for_tenant(tenant_id: str, max_chunks: int = 30) -> dict:
    """Pro Tenant: letzte N memory_chunks scannen + Vorschläge schreiben."""
    from services.llm import llm_service, set_llm_tenant

    set_llm_tenant(tenant_id)
    out = {
        "tenant_id": tenant_id,
        "chunks_scanned": 0,
        "suggestions": 0,
        "auto_applied": 0,
        "conflicts": 0,
    }

    with sync_session_factory() as db:
        rows = db.execute(
            text(f"""
                SELECT id, content_text, source_type, created_at
                FROM memory_chunks
                WHERE tenant_id = :tid
                  AND content_text IS NOT NULL
                  AND char_length(content_text) >= 30
                  AND {SQL_OHNE_ANWEISUNGEN}
                  AND {SQL_NICHT_GELOESCHT}
                ORDER BY created_at DESC
                LIMIT :n
            """),
            {"tid": tenant_id, "n": max_chunks},
        ).fetchall()
        out["chunks_scanned"] = len(rows)
        if not rows:
            return out

        profile = db.execute(
            select(CompanyProfile).where(CompanyProfile.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if profile is None:
            profile = CompanyProfile(tenant_id=tenant_id)
            db.add(profile)
            db.flush()

        existing_by_field: dict[str, float] = {}
        prov_rows = db.execute(
            text("""
                SELECT field_name, MAX(confidence) AS max_conf
                FROM profile_field_provenance
                WHERE tenant_id = :tid AND applied = true
                GROUP BY field_name
            """),
            {"tid": tenant_id},
        ).fetchall()
        for r in prov_rows:
            existing_by_field[r.field_name] = float(r.max_conf or 0)

        combined_text = "\n\n---\n\n".join(
            f"[{r.source_type}, {r.created_at.isoformat() if r.created_at else ''}]\n{r.content_text[:1500]}"
            for r in rows
        )[:10000]

        try:
            # Should-Fix-Hinweis: asyncio.run() in einem Celery-Task ist korrekt,
            # weil Celery sync Tasks in einem eigenen Thread ohne laufende Event-Loop
            # ausführt. asyncio.run() erzeugt eine neue Loop und schließt sie danach.
            # Falls dieser Task je in einem async Kontext (z.B. FastAPI Background Task)
            # gerufen wird, würde asyncio.run() mit RuntimeError "cannot run nested
            # event loop" scheitern. Dann: nest_asyncio.apply() vor dem run() einfügen
            # oder llm_service.complete_json_sync() verwenden falls verfügbar.
            # Aktuell: Celery-only → kein Problem. (#148-followup bei Async-Migration)
            data = asyncio.run(
                llm_service.complete_json(
                    prompt="## TEXT:\n" + combined_text,
                    system=EXTRACTION_PROMPT,
                    model="gemini-flash",
                    purpose="profile_extraction",
                )
            )
        except Exception as e:
            logger.warning(f"P06 LLM-call failed for {tenant_id}: {e}")
            return out

        extractions = data.get("extractions", []) or []
        voice_conf = SOURCE_TRUST["voice_extracted"]
        now = datetime.datetime.utcnow()

        for ex in extractions:
            field_name = ex.get("field", "").strip()
            value = ex.get("value")
            conf = float(ex.get("confidence", 0.7))
            if not field_name or value is None:
                continue
            conf = min(conf, voice_conf + 0.1)

            existing_conf = existing_by_field.get(field_name, 0)
            if existing_conf > conf:
                out["conflicts"] += 1
                db.add(
                    ProfileFieldProvenance(
                        tenant_id=tenant_id,
                        field_name=field_name,
                        source="voice_extracted",
                        value=str(value)[:500],
                        confidence=conf,
                        applied=False,
                        reviewed_by="auto_rejected_lower_trust",
                    )
                )
                continue

            will_apply = conf >= AUTO_APPLY_THRESHOLD
            db.add(
                ProfileFieldProvenance(
                    tenant_id=tenant_id,
                    field_name=field_name,
                    source="voice_extracted",
                    value=str(value)[:500],
                    confidence=conf,
                    applied=will_apply,
                    applied_at=now if will_apply else None,
                    reviewed_by="p06_auto" if will_apply else None,
                )
            )
            out["suggestions"] += 1

            if will_apply and hasattr(profile, field_name):
                cast_value: Any = value
                if field_name in ("founded_year", "headcount"):
                    try:
                        cast_value = int(re.search(r"\d+", str(value)).group(0))
                    except (AttributeError, ValueError, TypeError):
                        continue
                elif field_name in ("usp", "target_audience", "values_short"):
                    cast_value = _truncate(str(value), 200)
                else:
                    cast_value = _truncate(str(value), 250) if isinstance(value, str) else value
                setattr(profile, field_name, cast_value)
                if field_name == "industry":
                    db.execute(
                        text("UPDATE tenants SET industry = :i WHERE id = :tid"),
                        {"i": cast_value, "tid": tenant_id},
                    )
                out["auto_applied"] += 1
                existing_by_field[field_name] = conf

        profile.updated_at = now
        db.commit()
    logger.info(f"P06 done: {out}")
    return out


@celery_app.task(name="tasks.p06_profile_extractor_task.run_all")
def run_all(max_chunks: int = 30) -> dict:
    """Master-Task: für alle Tenants P06 ausführen."""
    with sync_session_factory() as db:
        rows = db.execute(text("SELECT id FROM tenants WHERE enabled = true")).fetchall()

    total = {"tenants": 0, "errors": 0}
    for r in rows:
        try:
            run_for_tenant.delay(str(r.id), max_chunks=max_chunks)
            total["tenants"] += 1
        except Exception as e:
            logger.warning(f"P06 enqueue failed for {r.id}: {e}")
            total["errors"] += 1
    return total
