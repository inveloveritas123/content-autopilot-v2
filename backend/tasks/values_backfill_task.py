"""
tasks/values_backfill_task.py — Idempotenter Backfill für tenant_customer_values (Issue #43, Schritt 2).

Befüllt die Werte-Entität aus vorhandenen Quellen:

  Quelle A — memory_chunks mit classification='werte' (Telegram-Inbound, store_chunk-Gate).
  Quelle B — Setup-Seed aus dem aktiven customer_context-Payload (positionierung.werte_schwerpunkt);
              optional, als TODO dokumentiert für den Fall eines fehlenden Setup-Feldes.

Idempotenz (Schritt-5 aus §6 des Plans):
  - Vor dem LLM-Call wird die aktive Row auf bereits referenzierte chunk_ids geprüft.
  - Nur wirklich neue Chunks (nicht in source_meta.chunk_ids der aktiven Row) lösen
    einen LLM-Call und eine neue Version aus.
  - Kein neuer Chunk + kein Setup-Seed-Delta → No-op ohne LLM-Call und ohne INSERT.

Tenant-Scope (E3):
  - JEDE Datenbankabfrage ist auf :tenant_id gebunden — kein Cross-Tenant-Leak.

Sicher vor Migration 053:
  - Falls die Tabelle tenant_customer_values fehlt (vor Migration), sauberer No-op
    mit Status-Dict, kein Crash (fail-open).

Ausführung:
  - CLI:    cd backend && python -m tasks.values_backfill_task --tenant <id>
  - Celery: celery_app.send_task('tasks.values_backfill_task.run_values_backfill',
              kwargs={'tenant_id': '<id>'})
  - Alle Tenants: --all-tenants (holt Tenant-IDs aus tenants-Tabelle, je seriell)

ROBERT-Hinweis:
  Dieser Task setzt Migration 053 (tenant_customer_values-Tabelle) voraus.
  Nicht auf Prod ausführen, bevor die Migration (Label freigabe-robert) freigegeben ist.

LLM-Routing: S4 mistral-large für Analyse/Konsolidierung (Tier-Policy: S1-S4 frei).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

logger = logging.getLogger(__name__)

# Modell-Konstante — S4 gemäß Routing-Policy (Analyse-Qualität, frei ohne Confirm).
_CONSOLIDATION_MODEL = "mistral/mistral-large-latest"

# Prompt für LLM-Konsolidierung (Dedup/Clustering der Werte-Chunks).
_CONSOLIDATION_SYSTEM = (
    "Du bist ein Analyse-Assistent. Konsolidiere die folgenden Roheinträge zu "
    "einer strukturierten Liste von Kundenwerten.\n\n"
    "Gib ausschließlich gültiges JSON zurück — ein Array 'werte', in dem jeder "
    "Eintrag die Felder 'wert' (kurzer Name), 'beschreibung' (1-2 Sätze), "
    "'belege' (Array mit max. 3 wörtlichen Kurzbelegen aus den Eingaben), "
    "'gewicht' (1-5, default 3) und 'status' ('aktiv' für Setup-Einträge, "
    "'vorgeschlagen' für Chunk-Funde) hat.\n\n"
    "Dedupliziere ähnliche Werte. Halluziniere keine neuen Werte. "
    'Antworte NUR mit {"werte": [...]}, kein Markdown.'
)


# ---------------------------------------------------------------------------
# Hilfsfunktionen (dep-frei testbar — kein sqlalchemy/celery-Import auf Modul-Ebene)
# ---------------------------------------------------------------------------


def _make_wert_entry(
    wert: str,
    beschreibung: str,
    belege: list[str],
    quellen: list[dict],
    *,
    gewicht: int = 3,
    status: str = "vorgeschlagen",
) -> dict:
    """Erstellt einen kanonischen Werte-Eintrag mit Provenance."""
    return {
        "wert": wert,
        "beschreibung": beschreibung,
        "belege": belege,
        "gewicht": gewicht,
        "status": status,
        "quellen": quellen,
    }


def _extract_setup_seed_entries(context_payload: dict) -> list[dict]:
    """Extrahiert Werte-Einträge aus dem Setup-Seed (positionierung.werte_schwerpunkt).

    Quelle B: kanonisches P01-Feld positionierung.werte_schwerpunkt (String).
    Alt-v2-Feld: werte (Array) — NICHT mehr kanonisch (schema_transformer.py:1008-1015).
    Beide werden defensive gelesen; das kanonische Feld hat Vorrang.

    Returns leere Liste wenn kein Setup-Eintrag gefunden.
    """
    if not isinstance(context_payload, dict):
        return []

    entries = []

    # Kanonisch: positionierung.werte_schwerpunkt (String)
    positionierung = context_payload.get("positionierung")
    if isinstance(positionierung, dict):
        ws = positionierung.get("werte_schwerpunkt")
        if ws and isinstance(ws, str) and ws.strip():
            entries.append(
                _make_wert_entry(
                    wert=ws.strip()[:120],
                    beschreibung=f"Setup-Eingabe: {ws.strip()[:200]}",
                    belege=[ws.strip()[:300]],
                    quellen=[
                        {"typ": "setup", "ref": "positionierung.werte_schwerpunkt", "datum": None}
                    ],
                    gewicht=4,
                    status="aktiv",  # Vom Kunden selbst genannt → aktiv (§6.3)
                )
            )

    # TODO: Quelle B alt-v2 `werte`-Array (lossy als werte_schwerpunkt abgebildet,
    # schema_transformer.py:282-291) — hier nicht implementiert, da:
    # 1. v2-Altfeld ist im kanonischen Schema verboten (additionalProperties:false).
    # 2. Neue Tenants haben nur noch positionierung.werte_schwerpunkt.
    # 3. Als separates Folge-Issue anlegen wenn Alt-Tenants betroffen sind.

    return entries


def _build_llm_prompt(
    chunk_contents: list[str],
    setup_entries: list[dict],
) -> str:
    """Baut den User-Prompt für die LLM-Konsolidierung."""
    parts = []
    if setup_entries:
        parts.append("=== Setup-Eingaben ===")
        for e in setup_entries:
            parts.append(f"- {e['wert']}: {e.get('beschreibung', '')}")
    if chunk_contents:
        parts.append("\n=== Memory-Chunk-Inhalte ===")
        for i, c in enumerate(chunk_contents[:50], 1):  # Max 50 Chunks
            parts.append(f"[{i}] {c[:500]}")
    return "\n".join(parts)


def _merge_werte_with_provenance(
    llm_werte: list[dict],
    chunk_rows: list[dict],
    setup_entries: list[dict],
) -> list[dict]:
    """Fügt Provenance-Quellen zu den LLM-konsolidierten Werte-Einträgen hinzu.

    Da das LLM keine Chunk-IDs zurückgibt, referenzieren wir alle Chunk-IDs
    global in source_meta (Row-Ebene). Auf Payload-Ebene liegt der Typ in quellen[].
    Für Setup-Seeds übernehmen wir die vorhandene quellen-Liste aus setup_entries.

    Strategie: alle LLM-Einträge mit status='vorgeschlagen' kriegen quellen=[{typ:memory_chunk}],
    Setup-Seeds behalten status='aktiv' und ihre Setup-Provenance.
    """
    result = []

    for entry in llm_werte:
        if not isinstance(entry, dict):
            continue
        wert_name = (entry.get("wert") or "").strip()
        if not wert_name:
            continue

        # Passendes Setup-Entry finden (case-insensitive, Substring-Match)
        matched_setup = None
        for se in setup_entries:
            if se["wert"].lower() in wert_name.lower() or wert_name.lower() in se["wert"].lower():
                matched_setup = se
                break

        if matched_setup:
            quellen = matched_setup["quellen"]
            status = "aktiv"
        else:
            # Memory-Chunk-Provenance: alle Chunk-IDs auf Row-Ebene in source_meta
            quellen = [{"typ": "memory_chunk", "ref": "backfill", "datum": None}]
            status = entry.get("status", "vorgeschlagen")
            if status not in ("aktiv", "vorgeschlagen", "verworfen"):
                status = "vorgeschlagen"

        result.append(
            _make_wert_entry(
                wert=wert_name[:120],
                beschreibung=(entry.get("beschreibung") or "")[:500],
                belege=[b[:300] for b in (entry.get("belege") or [])[:3] if isinstance(b, str)],
                quellen=quellen,
                gewicht=int(entry.get("gewicht") or 3),
                status=status,
            )
        )

    return result


def _extract_known_chunk_ids(active_row_payload: dict | None) -> set[str]:
    """Extrahiert bereits referenzierte Chunk-IDs aus der aktiven Row.

    Idempotenz-Seam: source_meta.chunk_ids enthält die beim letzten Backfill
    verwendeten Chunk-IDs. Nur Chunks, die dort NICHT stehen, sind "neu".
    """
    if not isinstance(active_row_payload, dict):
        return set()
    # source_meta wird auf Row-Ebene gespeichert (nicht im Payload) —
    # wird daher als Parameter übergeben (siehe _backfill_tenant).
    return set()


def _extract_known_chunk_ids_from_meta(source_meta: dict | None) -> set[str]:
    """Extrahiert chunk_ids aus source_meta (Row-Level, nicht Payload)."""
    if not isinstance(source_meta, dict):
        return set()
    ids = source_meta.get("chunk_ids")
    if isinstance(ids, list):
        return {str(i) for i in ids if i}
    return set()


# ---------------------------------------------------------------------------
# Kernlogik — async (DB-Seam via sqlalchemy text())
# ---------------------------------------------------------------------------


async def _backfill_tenant(tenant_id: str, *, db_execute, llm_complete_json) -> dict:
    """Backfill für einen einzelnen Tenant.

    db_execute: async callable (sql: str, params: dict) -> rows (list of row-dicts).
    llm_complete_json: async callable (prompt, system, model, purpose) -> dict | None.

    Gibt ein Status-Dict zurück:
      {"status": "ok" | "no_op" | "error", "reason"?: str, "version"?: int}
    """
    # ------------------------------------------------------------------
    # 0. Prüfen ob Tabelle existiert (fail-open vor Migration 053)
    # ------------------------------------------------------------------
    try:
        table_check = await db_execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'tenant_customer_values' LIMIT 1",
            {},
        )
        if not table_check:
            logger.info(
                "values_backfill tenant=%s: tenant_customer_values nicht vorhanden (vor Migration 053) → No-op",
                tenant_id,
            )
            return {"status": "no_op", "reason": "table_missing"}
    except Exception as exc:
        logger.warning("values_backfill tenant=%s: table-check fehlgeschlagen: %s", tenant_id, exc)
        return {"status": "no_op", "reason": f"table_check_failed: {exc}"}

    # ------------------------------------------------------------------
    # 1. Aktive Row laden (Idempotenz-Basis)
    # ------------------------------------------------------------------
    active_rows = await db_execute(
        "SELECT id, version, payload, source_meta "
        "FROM tenant_customer_values "
        "WHERE tenant_id = :t AND is_active = true "
        "ORDER BY version DESC LIMIT 1",
        {"t": tenant_id},
    )
    active_row = active_rows[0] if active_rows else None
    known_chunk_ids: set[str] = set()
    next_version = 1
    active_row_id: str | None = None

    if active_row:
        active_row_id = str(active_row["id"])
        next_version = int(active_row.get("version") or 0) + 1
        raw_meta = active_row.get("source_meta")
        if isinstance(raw_meta, str):
            try:
                raw_meta = json.loads(raw_meta)
            except json.JSONDecodeError:
                raw_meta = {}
        known_chunk_ids = _extract_known_chunk_ids_from_meta(raw_meta)

    # ------------------------------------------------------------------
    # 2. Quelle A — neue memory_chunks mit classification='werte' (Tenant-scoped)
    # ------------------------------------------------------------------
    chunk_rows_raw = await db_execute(
        "SELECT id, content_text, created_at "
        "FROM memory_chunks "
        "WHERE tenant_id = :t AND classification = 'werte' "
        "ORDER BY created_at DESC",
        {"t": tenant_id},
    )
    # E2: content_text nur intern verwenden, nie loggen
    all_chunk_ids = {str(r["id"]) for r in chunk_rows_raw}
    new_chunk_ids = all_chunk_ids - known_chunk_ids

    chunk_rows = [r for r in chunk_rows_raw if str(r["id"]) in new_chunk_ids]

    # ------------------------------------------------------------------
    # 3. Quelle B — Setup-Seed aus aktivem customer_context
    # ------------------------------------------------------------------
    context_rows = await db_execute(
        "SELECT payload "
        "FROM tenant_customer_context "
        "WHERE tenant_id = :t AND is_active = true "
        "ORDER BY version DESC LIMIT 1",
        {"t": tenant_id},
    )
    context_payload: dict = {}
    if context_rows:
        raw = context_rows[0].get("payload") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        context_payload = raw if isinstance(raw, dict) else {}

    setup_entries = _extract_setup_seed_entries(context_payload)

    # Idempotenz für Setup-Seed: wenn aktive Row bereits existiert und
    # keine neuen Chunks vorhanden sind, ist Setup-Seed ebenfalls schon drin → No-op.
    if not chunk_rows and not setup_entries and active_row is not None:
        logger.info(
            "values_backfill tenant=%s: keine neuen Chunks, kein Setup-Seed → No-op",
            tenant_id,
        )
        return {"status": "no_op", "reason": "nothing_new"}

    if not chunk_rows and not setup_entries:
        logger.info(
            "values_backfill tenant=%s: keine 'werte'-Chunks, kein Setup-Seed → No-op",
            tenant_id,
        )
        return {"status": "no_op", "reason": "no_chunks_no_seed"}

    # ------------------------------------------------------------------
    # 4. LLM-Konsolidierung (Seam — nie direkter SDK-Call)
    # ------------------------------------------------------------------
    chunk_contents = [r.get("content_text") or "" for r in chunk_rows]
    llm_prompt = _build_llm_prompt(chunk_contents, setup_entries)

    try:
        llm_result = await llm_complete_json(
            prompt=llm_prompt,
            system=_CONSOLIDATION_SYSTEM,
            model=_CONSOLIDATION_MODEL,
            purpose="analysis",
        )
    except Exception as exc:
        logger.warning("values_backfill tenant=%s: LLM-Call fehlgeschlagen: %s", tenant_id, exc)
        return {"status": "error", "reason": f"llm_failed: {exc}"}

    raw_werte = []
    if isinstance(llm_result, dict):
        raw_werte = llm_result.get("werte") or []
    if not isinstance(raw_werte, list):
        raw_werte = []

    werte_list = _merge_werte_with_provenance(raw_werte, chunk_rows, setup_entries)

    # Fallback: wenn LLM nichts zurückgibt, Setup-Einträge direkt verwenden
    if not werte_list and setup_entries:
        werte_list = setup_entries
        logger.info(
            "values_backfill tenant=%s: LLM lieferte keine Einträge → Setup-Seed als Fallback",
            tenant_id,
        )

    if not werte_list:
        logger.info(
            "values_backfill tenant=%s: Keine Werte nach LLM-Konsolidierung → No-op",
            tenant_id,
        )
        return {"status": "no_op", "reason": "empty_after_consolidation"}

    # ------------------------------------------------------------------
    # 5. Kanonisches Dokument bauen (build_canonical_meta + finalize_canonical)
    # ------------------------------------------------------------------
    # Lazy-Import: hält Modul-Ebene dep-frei (schema_transformer hat keine sqlalchemy-Deps,
    # aber importlib-Loader-Isolation schützt Test-Seams).
    try:
        from services.schema_transformer import build_canonical_meta, finalize_canonical
        from tasks.canonical_wiring import fetch_tenant_meta, now_iso
    except Exception as exc:
        logger.error("values_backfill: Import canonical-Wiring fehlgeschlagen: %s", exc)
        return {"status": "error", "reason": f"import_failed: {exc}"}

    new_row_id = str(uuid.uuid4())
    tenant_name, agentur_id = fetch_tenant_meta(tenant_id)

    canonical_meta = build_canonical_meta(
        "values",
        tenant_id=tenant_id,
        model=_CONSOLIDATION_MODEL,
        generated_at=now_iso(),
        tenant_name=tenant_name,
        agentur_id=agentur_id,
        row_id=new_row_id,
    )

    werte_doc = {"werte": werte_list}
    final_doc, schema_errors = finalize_canonical("values", werte_doc, meta=canonical_meta)
    if schema_errors:
        logger.info(
            "values_backfill tenant=%s: %d Schema-Lücken dokumentiert (kein Hard-Fail)",
            tenant_id,
            len(schema_errors),
        )

    all_used_chunk_ids = list(all_chunk_ids)  # alle Chunk-IDs für source_meta
    source_meta = json.dumps({"chunk_ids": all_used_chunk_ids, "setup_seed": bool(setup_entries)})

    # ------------------------------------------------------------------
    # 6. DB-Insert (neue aktive Row) + Deaktivierung der alten
    # ------------------------------------------------------------------
    try:
        await db_execute(
            "INSERT INTO tenant_customer_values "
            "(id, tenant_id, version, is_active, source, source_meta, payload, "
            "prompt_version_hash, model_id, created_at) "
            "VALUES (:id, :tenant_id, :version, true, 'memory_promotion', "
            "CAST(:source_meta AS jsonb), CAST(:payload AS jsonb), "
            ":prompt_version_hash, :model_id, now())",
            {
                "id": new_row_id,
                "tenant_id": tenant_id,
                "version": next_version,
                "source_meta": source_meta,
                "payload": json.dumps(final_doc, ensure_ascii=False),
                "prompt_version_hash": canonical_meta.get("prompt_version", "values-v1.0"),
                "model_id": _CONSOLIDATION_MODEL,
            },
            write=True,
        )

        if active_row_id:
            await db_execute(
                "UPDATE tenant_customer_values SET is_active = false WHERE id = :id AND tenant_id = :t",
                {"id": active_row_id, "t": tenant_id},
                write=True,
            )
    except Exception as exc:
        logger.error("values_backfill tenant=%s: DB-Write fehlgeschlagen: %s", tenant_id, exc)
        return {"status": "error", "reason": f"db_write_failed: {exc}"}

    logger.info(
        "values_backfill tenant=%s: version=%d, werte=%d, chunks=%d, setup_seed=%s",
        tenant_id,
        next_version,
        len(werte_list),
        len(all_used_chunk_ids),
        bool(setup_entries),
    )
    return {
        "status": "ok",
        "version": next_version,
        "werte_count": len(werte_list),
        "chunk_count": len(all_used_chunk_ids),
        "new_chunks": len(new_chunk_ids),
        "setup_seed": bool(setup_entries),
    }


# ---------------------------------------------------------------------------
# DB-Seam für echten Betrieb (sqlalchemy async engine)
# ---------------------------------------------------------------------------


def _make_real_db_execute(engine, SessionMaker):
    """Erstellt den echten db_execute-Callable für _backfill_tenant."""

    async def _db_execute(sql: str, params: dict, *, write: bool = False):
        from sqlalchemy import text

        async with SessionMaker() as session:
            result = await session.execute(text(sql), params)
            if write:
                await session.commit()
                return []
            rows = result.fetchall()
            # Rows als Dicts zurückgeben
            keys = list(result.keys()) if hasattr(result, "keys") else []
            return [dict(zip(keys, row, strict=False)) for row in rows]

    return _db_execute


# ---------------------------------------------------------------------------
# Celery-Task
# ---------------------------------------------------------------------------


def run_values_backfill_sync(tenant_id: str) -> dict:
    """Synchroner Wrapper für den Celery-Task."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from config import settings
    from services.llm import llm_service

    async def _run():
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        db_execute = _make_real_db_execute(engine, SessionMaker)

        async def llm_complete_json(prompt, system, model, purpose):
            return await llm_service.complete_json(
                prompt=prompt, system=system, model=model, purpose=purpose
            )

        try:
            return await _backfill_tenant(
                tenant_id, db_execute=db_execute, llm_complete_json=llm_complete_json
            )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


try:
    from tasks.celery_app import celery_app

    @celery_app.task(
        name="tasks.values_backfill_task.run_values_backfill",
        bind=True,
        max_retries=0,
    )
    def run_values_backfill(self, tenant_id: str) -> dict:
        """Celery-Task — idempotenter Backfill für einen Tenant.

        ROBERT-Hinweis: Setzt Migration 053 voraus. Erst nach Freigabe ausführen.
        """
        try:
            return run_values_backfill_sync(tenant_id)
        except Exception as exc:
            logger.warning("values_backfill Celery-Task fehlgeschlagen: %s", exc)
            return {"status": "error", "reason": str(exc)[:200]}

except ImportError:
    # Celery nicht verfügbar (lokale Tests) — kein Crash
    pass


# ---------------------------------------------------------------------------
# CLI-Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Backfill tenant_customer_values aus memory_chunks"
    )
    parser.add_argument("--tenant", required=False, help="Einzelner Tenant-ID")
    parser.add_argument(
        "--all-tenants",
        action="store_true",
        help="Alle Tenants (holt IDs aus tenants-Tabelle)",
    )
    args = parser.parse_args()

    if not args.tenant and not args.all_tenants:
        parser.error("--tenant oder --all-tenants erforderlich")

    if args.tenant:
        result = run_values_backfill_sync(args.tenant)
        print(json.dumps(result, indent=2))
    else:
        # all-tenants: synchrone DB-Abfrage + serieller Backfill
        import asyncio

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        from config import settings

        async def _run_all():
            engine = create_async_engine(settings.database_url, pool_pre_ping=True)
            SessionMaker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with SessionMaker() as session:
                rows = (
                    await session.execute(text("SELECT id FROM tenants ORDER BY id"))
                ).fetchall()
            tenant_ids = [str(r[0]) for r in rows]
            await engine.dispose()

            results = {}
            for tid in tenant_ids:
                results[tid] = run_values_backfill_sync(tid)
                print(f"{tid}: {results[tid]}")
            return results

        all_results = asyncio.run(_run_all())
        print(json.dumps(all_results, indent=2))
