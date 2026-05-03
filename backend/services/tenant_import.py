"""
TenantImportService — Validiert und importiert Tenant-Daten aus einem ZIP-Export.

Importiert nur eine sichere Teilmenge:
- sources.json      → Source (upsert by name+type)
- content_pieces.json → ContentPiece (merge=True: upsert by id, merge=False: delete+insert)
- content_ideas.json  → ContentIdea (merge=True: upsert by id, merge=False: delete+insert)

Schreibt nach jedem echten Import einen Audit-Eintrag in llm_call_logs
mit task_type="data_import".
"""
import io
import json
import uuid
import zipfile
from datetime import datetime
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.content_idea import ContentIdea
from models.content_piece import ContentPiece
from models.llm_call_log import LLMCallLog
from models.source import Source
from models.tenant import Tenant

_MAX_ZIP_BYTES = 100 * 1024 * 1024  # 100 MB
_SUPPORTED_SCHEMA_VERSION = "2.0.0"


def _safe_name(name: str) -> bool:
    """Prüft auf path-traversal in ZIP-Entry-Namen."""
    return not (name.startswith("/") or ".." in name.split("/"))


def _parse_zip(zip_bytes: bytes) -> zipfile.ZipFile:
    buf = io.BytesIO(zip_bytes)
    return zipfile.ZipFile(buf, "r")


def _read_json(zf: zipfile.ZipFile, name: str) -> Any:
    with zf.open(name) as f:
        return json.load(f)


def _to_uuid_or_none(val: Any) -> uuid.UUID | None:
    if val is None:
        return None
    try:
        return uuid.UUID(str(val))
    except (ValueError, AttributeError):
        return None


def _to_datetime_or_none(val: Any) -> datetime | None:
    if val is None:
        return None
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


class TenantImportService:
    async def validate_import(self, zip_bytes: bytes, tenant: Tenant) -> dict:
        """Gibt {"valid": bool, "errors": [...], "preview": {counts}} zurück."""
        errors = []
        preview = {}

        # 1. Größenlimit
        if len(zip_bytes) > _MAX_ZIP_BYTES:
            return {
                "valid": False,
                "errors": [f"ZIP zu groß: {len(zip_bytes) // (1024*1024)} MB (Max: 100 MB)"],
                "preview": {},
            }

        # 2. ZIP valide?
        try:
            zf = _parse_zip(zip_bytes)
        except zipfile.BadZipFile as exc:
            return {"valid": False, "errors": [f"Kein gültiges ZIP: {exc}"], "preview": {}}

        with zf:
            names = zf.namelist()

            # 3. Path-Traversal
            bad = [n for n in names if not _safe_name(n)]
            if bad:
                errors.append(f"Unsichere ZIP-Einträge: {bad}")

            # 4. manifest.json vorhanden?
            if "manifest.json" not in names:
                errors.append("manifest.json fehlt")
                return {"valid": False, "errors": errors, "preview": {}}

            try:
                manifest = _read_json(zf, "manifest.json")
            except Exception as exc:
                return {"valid": False, "errors": [f"manifest.json nicht lesbar: {exc}"], "preview": {}}

            # 5. Schema-Version
            if manifest.get("schema_version") != _SUPPORTED_SCHEMA_VERSION:
                errors.append(
                    f"Inkompatible schema_version: {manifest.get('schema_version')!r} "
                    f"(erwartet: {_SUPPORTED_SCHEMA_VERSION!r})"
                )

            # 6. tenant_id muss übereinstimmen
            manifest_tid = manifest.get("tenant_id")
            if str(tenant.id) != manifest_tid:
                errors.append(
                    f"tenant_id stimmt nicht überein: ZIP hat {manifest_tid!r}, "
                    f"aktueller Tenant ist {str(tenant.id)!r}"
                )

            # Preview-Counts aus dem ZIP (was würde importiert)
            for fname, label in [
                ("sources.json", "sources"),
                ("content_pieces.json", "content_pieces"),
                ("content_ideas.json", "content_ideas"),
            ]:
                if fname in names:
                    try:
                        rows = _read_json(zf, fname)
                        preview[label] = len(rows) if isinstance(rows, list) else 0
                    except Exception:
                        preview[label] = 0
                        errors.append(f"{fname} nicht lesbar")
                else:
                    preview[label] = 0

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "preview": preview,
        }

    async def execute_import(
        self,
        zip_bytes: bytes,
        tenant: Tenant,
        db: AsyncSession,
        merge: bool = True,
    ) -> dict:
        """
        Führt echten Import durch.
        merge=True → upsert (vorhandene Datensätze werden aktualisiert)
        merge=False → delete+insert (vorhandene Daten werden gelöscht)
        Gibt {"imported": {counts}, "errors": [...]} zurück.
        """
        validation = await self.validate_import(zip_bytes, tenant)
        if not validation["valid"]:
            return {"imported": {}, "errors": validation["errors"]}

        zf = _parse_zip(zip_bytes)
        imported_counts: dict[str, int] = {}
        errors = []

        with zf:
            # --- sources.json ---
            try:
                source_rows = _read_json(zf, "sources.json") if "sources.json" in zf.namelist() else []
                n_sources = await self._import_sources(source_rows, tenant, db, merge)
                imported_counts["sources"] = n_sources
            except Exception as exc:
                errors.append(f"sources.json Import-Fehler: {exc}")

            # --- content_ideas.json ---
            try:
                idea_rows = _read_json(zf, "content_ideas.json") if "content_ideas.json" in zf.namelist() else []
                n_ideas = await self._import_content_ideas(idea_rows, tenant, db, merge)
                imported_counts["content_ideas"] = n_ideas
            except Exception as exc:
                errors.append(f"content_ideas.json Import-Fehler: {exc}")

            # --- content_pieces.json ---
            try:
                piece_rows = _read_json(zf, "content_pieces.json") if "content_pieces.json" in zf.namelist() else []
                n_pieces = await self._import_content_pieces(piece_rows, tenant, db, merge)
                imported_counts["content_pieces"] = n_pieces
            except Exception as exc:
                errors.append(f"content_pieces.json Import-Fehler: {exc}")

        # Audit-Eintrag
        try:
            audit = LLMCallLog(
                tenant_id=tenant.id,
                task_type="data_import",
                model="n/a",
                prompt_tokens=0,
                completion_tokens=0,
                cost_cents=0.0,
                duration_ms=0,
                success=len(errors) == 0,
                error_message="; ".join(errors)[:500] if errors else None,
            )
            db.add(audit)
            await db.commit()
        except Exception as exc:
            errors.append(f"Audit-Eintrag fehlgeschlagen: {exc}")

        return {"imported": imported_counts, "errors": errors}

    # ── Interne Helfer ──────────────────────────────────────────────────────

    async def _import_sources(
        self, rows: list, tenant: Tenant, db: AsyncSession, merge: bool
    ) -> int:
        if not rows:
            return 0

        if not merge:
            await db.execute(delete(Source).where(Source.tenant_id == tenant.id))

        count = 0
        for row in rows:
            row_id = _to_uuid_or_none(row.get("id"))
            if row_id is None:
                continue

            existing = (
                await db.execute(select(Source).where(Source.id == row_id))
            ).scalar_one_or_none()

            if existing and merge:
                existing.name = str(row.get("name", existing.name))
                existing.type = str(row.get("type", existing.type))
                existing.url = row.get("url")
                existing.channel_id = row.get("channel_id")
                existing.language = str(row.get("language", existing.language))
                existing.is_active = bool(row.get("is_active", True))
                existing.keywords = row.get("keywords")
            elif not existing:
                db.add(Source(
                    id=row_id,
                    tenant_id=tenant.id,
                    name=str(row.get("name", "")),
                    type=str(row.get("type", "unknown")),
                    url=row.get("url"),
                    channel_id=row.get("channel_id"),
                    language=str(row.get("language", "de")),
                    is_active=bool(row.get("is_active", True)),
                    keywords=row.get("keywords"),
                ))
            count += 1

        await db.flush()
        return count

    async def _import_content_ideas(
        self, rows: list, tenant: Tenant, db: AsyncSession, merge: bool
    ) -> int:
        if not rows:
            return 0

        if not merge:
            await db.execute(delete(ContentIdea).where(ContentIdea.tenant_id == tenant.id))

        count = 0
        for row in rows:
            row_id = _to_uuid_or_none(row.get("id"))
            source_item_id = _to_uuid_or_none(row.get("source_item_id"))
            if row_id is None or source_item_id is None:
                continue

            existing = (
                await db.execute(select(ContentIdea).where(ContentIdea.id == row_id))
            ).scalar_one_or_none()

            if existing and merge:
                existing.title = str(row.get("title", existing.title))
                existing.description = str(row.get("description", existing.description))
                existing.angle = str(row.get("angle", existing.angle))
                existing.status = str(row.get("status", existing.status))
                existing.relevance_score = float(row.get("relevance_score", existing.relevance_score))
                existing.hook_suggestion = row.get("hook_suggestion")
                existing.entrepreneur_questions = row.get("entrepreneur_questions")
            elif not existing:
                db.add(ContentIdea(
                    id=row_id,
                    tenant_id=tenant.id,
                    source_item_id=source_item_id,
                    title=str(row.get("title", "")),
                    description=str(row.get("description", "")),
                    angle=str(row.get("angle", "meinung")),
                    status=str(row.get("status", "new")),
                    relevance_score=float(row.get("relevance_score", 0.0)),
                    hook_suggestion=row.get("hook_suggestion"),
                    entrepreneur_questions=row.get("entrepreneur_questions"),
                    source_quotes=row.get("source_quotes"),
                    source_context=row.get("source_context"),
                ))
            count += 1

        await db.flush()
        return count

    async def _import_content_pieces(
        self, rows: list, tenant: Tenant, db: AsyncSession, merge: bool
    ) -> int:
        if not rows:
            return 0

        if not merge:
            await db.execute(delete(ContentPiece).where(ContentPiece.tenant_id == tenant.id))

        count = 0
        for row in rows:
            row_id = _to_uuid_or_none(row.get("id"))
            source_item_id = _to_uuid_or_none(row.get("source_item_id"))
            if row_id is None or source_item_id is None:
                continue

            existing = (
                await db.execute(select(ContentPiece).where(ContentPiece.id == row_id))
            ).scalar_one_or_none()

            if existing and merge:
                existing.channel = str(row.get("channel", existing.channel))
                existing.content_text = str(row.get("content_text", existing.content_text))
                existing.status = str(row.get("status", existing.status))
                existing.content_metadata = row.get("content_metadata", existing.content_metadata) or {}
            elif not existing:
                db.add(ContentPiece(
                    id=row_id,
                    tenant_id=tenant.id,
                    source_item_id=source_item_id,
                    channel=str(row.get("channel", "linkedin")),
                    content_text=str(row.get("content_text", "")),
                    status=str(row.get("status", "draft")),
                    content_metadata=row.get("content_metadata") or {},
                    idea_id=_to_uuid_or_none(row.get("idea_id")),
                    approved_by=row.get("approved_by"),
                    approved_at=_to_datetime_or_none(row.get("approved_at")),
                    approval_method=row.get("approval_method"),
                ))
            count += 1

        await db.flush()
        return count
