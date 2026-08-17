"""Hard-Delete-Cron für DSGVO Soft-Deletes nach 30 Tagen Recovery-Cooldown.

Issue #148, Welle E. Daily 04:00.

Critical #2: Hard-Delete per deletion_request_id FK (kein BETWEEN-Window mehr).
Critical #4: Cascade auf llm_call_logs.
Should-Fix: Per-Iteration-Transaction (async with db.begin() pro Request).

W6-Härtung (Issue #156-followup): _delete_nc_files() ist vollständig
implementiert (vorher Stub). Löscht die tenant-spezifischen NC-Dateien
(Transkripte/Analysen/Content) via services.nextcloud.nextcloud_client.

memory_chunks-Embeddings: Die embedding-Spalte (vector(768|1536), Migration
038/049) lebt AUF der memory_chunks-Zeile selbst — es gibt keine separate
Embedding-Tabelle. Der Hard-Delete-Statement in _HARD_DELETE_TABLES
("DELETE FROM memory_chunks WHERE ...") löscht damit die Zeile inkl.
Embedding in einem Schritt. Keine zusätzliche Kaskade nötig — bereits
vollständig abgedeckt (verifiziert 2026-07-21).
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from models.base import sync_session_factory
from services.rls import set_rls_bypass_sync, set_rls_tenant_sync
from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# Critical #1 / #4: statische Whitelist — kein f-String mit variablem Tabellennamen.
# Schlüssel = Tabellenname, Wert = Hard-Delete-Statement.
_HARD_DELETE_TABLES: dict[str, str] = {
    "memory_chunks": (
        "DELETE FROM memory_chunks " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "content_pieces": (
        "DELETE FROM content_pieces " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "content_ideas": (
        "DELETE FROM content_ideas " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    "source_items": (
        "DELETE FROM source_items " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    # Critical #4: llm_call_logs in Hard-Delete-Cascade einbeziehen.
    "llm_call_logs": (
        "DELETE FROM llm_call_logs " "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
    # DSGVO Art. 17 / R1: telegram_message_log (Voice-Transkripte + Telegram-Payloads)
    # muss hard-deleted werden. Spalten deletion_request_id + deleted_at seit Mig. 047.
    "telegram_message_log": (
        "DELETE FROM telegram_message_log "
        "WHERE tenant_id = :tid AND deletion_request_id = :req_id"
    ),
}


# NC-Settings-Keys deren Pfade beim Hard-Delete auf Nextcloud bereinigt werden.
# Quelle: api/tenants.py SettingsUpdate (nc_transcript_path, nc_analysis_path,
# nc_content_path) — die tenant-spezifischen Ordner unter denen Transkripte,
# Analysen und generierter Content abgelegt werden.
_NC_PATH_SETTINGS_KEYS: tuple[str, ...] = (
    "nc_transcript_path",
    "nc_analysis_path",
    "nc_content_path",
)


def _tenant_nc_paths(tenant_id: str) -> list[str]:
    """Liest die tenant-spezifischen NC-Pfade aus tenants.settings.

    Bewusst über eine eigene, kurze DB-Session (statt die Purge-Transaktion
    zu teilen) — ein Fehler hier darf die Hard-Delete-Transaktion nicht
    beeinflussen.
    """
    paths: list[str] = []
    try:
        with sync_session_factory() as db:
            row = db.execute(
                text("SELECT settings FROM tenants WHERE id = :tid"),
                {"tid": tenant_id},
            ).fetchone()
        if row and row.settings:
            settings = row.settings
            for key in _NC_PATH_SETTINGS_KEYS:
                path = settings.get(key)
                if path:
                    paths.append(path)
    except Exception as exc:
        logger.error(
            "Konnte NC-Pfade für tenant=%s nicht laden (Settings-Lookup fehlgeschlagen): %s",
            tenant_id,
            exc,
        )
    return paths


async def _delete_nc_files_async(tenant_id: str, request_id: str) -> list[str]:
    """Löscht rekursiv alle Dateien unter den tenant-spezifischen NC-Pfaden.

    Gibt eine Liste von Fehlermeldungen zurück (leer = alles ok oder nichts
    zu tun). Wirft bewusst nichts — NC-Nichterreichbarkeit darf den
    Hard-Delete-Cron nicht blockieren (DB-Löschung hat bereits stattgefunden).
    """
    from services.nextcloud import nextcloud_client

    errors: list[str] = []
    paths = _tenant_nc_paths(tenant_id)

    if not paths:
        logger.info(
            "NC-File-Löschung für tenant=%s request=%s: keine nc_*_path-Settings, nichts zu tun",
            tenant_id,
            request_id,
        )
        return errors

    for base_path in paths:
        try:
            files = await nextcloud_client.list_files_recursive(base_path, extension="")
        except Exception as exc:
            msg = f"NC list_folder fehlgeschlagen für path={base_path}: {exc}"
            logger.error("NC-File-Löschung tenant=%s request=%s: %s", tenant_id, request_id, msg)
            errors.append(msg)
            continue

        # Auch den Basis-Ordner selbst löschen (nicht nur die enthaltenen Dateien) —
        # WebDAV DELETE auf einen Ordner entfernt ihn samt Inhalt rekursiv, daher
        # reicht ein einzelner Delete-Call auf base_path. list_files_recursive
        # oben dient nur der Diagnose/dem Logging (Anzahl betroffener Dateien).
        ok = await nextcloud_client.delete_file(base_path)
        if not ok:
            msg = f"NC delete_file fehlgeschlagen für path={base_path}"
            logger.error(
                "NC-File-Löschung tenant=%s request=%s: %s (files_found=%d)",
                tenant_id,
                request_id,
                msg,
                len(files),
            )
            errors.append(msg)
        else:
            logger.info(
                "NC-File-Löschung tenant=%s request=%s: path=%s gelöscht (files_found=%d)",
                tenant_id,
                request_id,
                base_path,
                len(files),
            )

    return errors


def _delete_nc_files(tenant_id: str, request_id: str) -> list[str]:
    """Löscht die NC-Dateien (Transkripte/Analysen/Content) eines Tenants beim Hard-Delete.

    Issue #156-followup: vollständige Implementierung (vorher Stub).
    Robust: NC nicht erreichbar → loggen + weiter, DB-Löschung ist bereits
    passiert und darf nicht rückgängig gemacht/blockiert werden. Gibt eine
    Liste von Fehlermeldungen zurück (leer bei Erfolg), damit der Aufrufer
    sie im deletion_requests.notes-Feld vermerken kann.
    """
    try:
        return asyncio.run(_delete_nc_files_async(tenant_id, request_id))
    except Exception as exc:
        msg = f"NC-Löschung unerwartet fehlgeschlagen: {exc}"
        logger.error("NC-File-Löschung für tenant=%s request=%s: %s", tenant_id, request_id, msg)
        return [msg]


@celery_app.task(name="tasks.deletion_purge_task.purge_expired")
def purge_expired() -> dict:
    """Findet abgelaufene soft-deletes und macht hard-delete (per deletion_request_id FK)."""
    out = {"requests_processed": 0, "rows_purged": {}}

    purged_total: dict[str, int] = {table: 0 for table in _HARD_DELETE_TABLES}

    with sync_session_factory() as db:
        # Cross-Tenant-Cron: holt faellige Loeschauftraege ALLER Tenants.
        # deletion_requests traegt seit Migration 058 FORCE ROW LEVEL SECURITY —
        # ohne Bypass findet der Purge keinen einzigen Auftrag mehr.
        # ⛔ Das waere ein DSGVO-Befund, kein Schoenheitsfehler: Art. 17
        # (Recht auf Loeschung) wuerde still nicht mehr vollzogen, waehrend der
        # Cron gruen durchlaeuft und "0 verarbeitet" meldet.
        set_rls_bypass_sync(db, True)
        rows = db.execute(
            text("""
            SELECT id, tenant_id, mode, affected_records
            FROM deletion_requests
            WHERE status = 'soft_deleted'
              AND recovery_until IS NOT NULL
              AND recovery_until < NOW()
            ORDER BY requested_at ASC
            LIMIT 50
        """)
        ).fetchall()

    # Should-Fix: Per-Iteration-Transaction — jede Anfrage in eigenem Commit.
    # Verhindert dass ein Fehler in Request N alle vorherigen N-1 Commits rolled back.
    for r in rows:
        tenant_id = r.tenant_id
        affected = r.affected_records or {}
        req_id = r.id

        try:
            with sync_session_factory() as db:
                # ⛔ NEUE Session pro Loeschauftrag — der Bypass der Lese-Session
                # oben gilt hier NICHT. Alle Statements sind auf diesen einen
                # Tenant gescopet (WHERE tenant_id = :tid), also der enge Weg.
                # Ohne Kontext traefen die DELETEs 0 Zeilen und der Auftrag
                # wuerde als erledigt markiert, OHNE dass Daten geloescht sind:
                # ein stiller Verstoss gegen DSGVO Art. 17 mit gruener Bilanz.
                set_rls_tenant_sync(db, tenant_id)
                for table, stmt in _HARD_DELETE_TABLES.items():
                    if affected.get(table, 0) > 0:
                        res = db.execute(
                            text(stmt),
                            {"tid": tenant_id, "req_id": req_id},
                        )
                        purged_total[table] += res.rowcount or 0

                db.execute(
                    text(
                        "UPDATE deletion_requests "
                        "SET status = 'hard_deleted', hard_deleted_at = NOW() "
                        "WHERE id = :id"
                    ),
                    {"id": req_id},
                )
                db.commit()

            # NC-Files nach Hard-Delete bereinigen (non-blocking — DB-Löschung ist
            # bereits committed und darf durch NC-Fehler nicht beeinflusst werden).
            nc_errors = _delete_nc_files(str(tenant_id), str(req_id))
            if nc_errors:
                # Fehler im Deletion-Request-Status vermerken (notes-Feld), damit
                # er im Audit-Trail sichtbar bleibt, auch wenn die Datenlöschung
                # selbst erfolgreich war. Eigene, kurze Transaktion — ein Fehler
                # hier darf den bereits erfolgreichen Hard-Delete nicht zurückrollen.
                try:
                    with sync_session_factory() as db:
                        db.execute(
                            text(
                                "UPDATE deletion_requests SET notes = "
                                "COALESCE(notes || E'\\n', '') || :note WHERE id = :id"
                            ),
                            {
                                "id": req_id,
                                "note": f"NC-Cleanup-Fehler: {'; '.join(nc_errors)[:900]}",
                            },
                        )
                        db.commit()
                except Exception as note_exc:
                    logger.error(
                        "Konnte NC-Cleanup-Fehler nicht in deletion_requests.notes "
                        "vermerken für request=%s: %s",
                        req_id,
                        note_exc,
                    )

            out["requests_processed"] += 1

        except Exception as exc:
            logger.error(
                "Hard-Delete fehlgeschlagen für deletion_request=%s tenant=%s: %s",
                req_id,
                tenant_id,
                exc,
            )

    out["rows_purged"] = purged_total
    logger.info("Deletion-purge cron done: %s", out)
    return out
