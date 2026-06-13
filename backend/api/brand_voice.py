"""
Brand-Voice API Endpoints (Issue #59).

POST   /api/brand-voice/upload           — MD/JSON hochladen, Pipeline triggern
POST   /api/brand-voice/import-source    — NC-Import starten
POST   /api/brand-voice/regenerate       — Transcript-basierte Regenerierung
GET    /api/brand-voice/{tenant_id}      — Aktive Profile + kompakte History
PATCH  /api/brand-voice/{tenant_id}/{profile_type}/field  — Einzelfeld editieren
GET    /api/brand-voice/pipeline/{run_id} — Pipeline-Run-Status abrufen
"""

import copy
import html
import json
import logging
import secrets as _secrets
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.brand_voice_drift_helpers import apply_drift_changes, get_entity_table
from dependencies import get_db, get_tenant, get_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# In-Memory Rate-Limiter (pro API-Key, Upload-Endpunkte)
# ---------------------------------------------------------------------------

_upload_counter: dict[str, list[datetime]] = defaultdict(list)
UPLOAD_RATE_LIMIT = 10  # Anfragen pro Minute


def _check_rate_limit(api_key: str) -> None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=60)
    _upload_counter[api_key] = [t for t in _upload_counter[api_key] if t >= cutoff]
    if len(_upload_counter[api_key]) >= UPLOAD_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit: max 10 Uploads/Minute",
        )
    _upload_counter[api_key].append(now)


# ---------------------------------------------------------------------------
# Sanitizer fuer PATCH-Werte (XSS-Schutz fuer String-Felder)
# ---------------------------------------------------------------------------


def _sanitize_value(v: Any) -> Any:
    if isinstance(v, str):
        return html.escape(v, quote=True)
    return v


# ---------------------------------------------------------------------------
# Allow-List editierbarer Felder pro Profil-Typ
# ---------------------------------------------------------------------------

EDITABLE_ROOT_KEYS: dict[str, list[str]] = {
    "customer_context": ["kernbotschaft", "zielgruppe", "expertise", "werte"],
    "voice_profile": [
        "tonalitaet",
        "kernthemen",
        "stilprinzipien",
        "wortschatz",
        "schreibrhythmus",
        "vermeidungsregeln",
    ],
    "audience_avatar": [
        "hauptperson",
        "kernschmerzen",
        "transformation",
        "einwaende",
        "kaufmotive",
        "sprachmuster",
    ],
}

# Tabellenzuordnung pro Profil-Typ (nur Code-Konstanten, kein User-Input)
_PROFILE_TABLE: dict[str, str] = {
    "customer_context": "tenant_customer_context",
    "voice_profile": "tenant_voice_profile",
    "audience_avatar": "tenant_audience_avatar",
}

# SQL-Strings werden einmalig bei Modul-Import aus der Whitelist-Konstante gebaut —
# zur Runtime fließt kein User-Input in Tabellennamen ein.
_SQL: dict[str, dict[str, str]] = {
    pt: {
        "select_active": (
            f"SELECT id, payload, version, created_at, source FROM {tbl} "
            f"WHERE tenant_id = :t AND is_active = true"
        ),
        "select_history": (
            f"SELECT version, created_at, source FROM {tbl} "
            f"WHERE tenant_id = :t ORDER BY version DESC LIMIT 10"
        ),
        "select_active_for_edit": (
            f"SELECT id, payload, version FROM {tbl} " f"WHERE tenant_id = :t AND is_active = true"
        ),
        "insert": (
            f"INSERT INTO {tbl} (tenant_id, version, is_active, source, payload, "
            f"prompt_version_hash, model_id) "
            f"VALUES (:tenant_id, :version, true, 'manual_edit', CAST(:payload AS jsonb), '', '')"
        ),
        "deactivate": f"UPDATE {tbl} SET is_active = false WHERE id = :id",
    }
    for pt, tbl in _PROFILE_TABLE.items()
}


# ---------------------------------------------------------------------------
# Request-Modelle
# ---------------------------------------------------------------------------


class UploadRequest(BaseModel):
    type: Literal["voice", "context", "avatar"]
    format: Literal["md", "json"]
    content: str


class ImportSourceRequest(BaseModel):
    type: Literal["voice", "context", "avatar"]
    source_adapter: Literal["nc"]
    path: str


class RegenerateRequest(BaseModel):
    sources: dict


class FieldEditRequest(BaseModel):
    field_path: str
    new_value: Any


# ---------------------------------------------------------------------------
# Hilfsfunktion: verschachteltes Feld in einem dict setzen
# ---------------------------------------------------------------------------


def _set_nested(d: dict, path: str, value: Any) -> None:
    """Setzt `value` im dict `d` anhand eines Punkt-getrennten Pfads."""
    parts = path.split(".")
    cursor = d
    for part in parts[:-1]:
        if not isinstance(cursor, dict):
            raise ValueError(f"Pfad '{path}' nicht navigierbar — Zwischen-Element kein dict")
        if part not in cursor:
            cursor[part] = {}
        cursor = cursor[part]
    if not isinstance(cursor, dict):
        raise ValueError(f"Pfad '{path}' nicht navigierbar — Blatt-Eltern kein dict")
    cursor[parts[-1]] = value


# ---------------------------------------------------------------------------
# POST /brand-voice/upload
# ---------------------------------------------------------------------------


@router.post("/brand-voice/upload", status_code=202)
async def upload_brand_voice(
    data: UploadRequest,
    project_id: str | None = Query(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """MD- oder JSON-Datei hochladen und Setup-Pipeline starten."""
    _check_rate_limit(x_api_key)

    # Groessenvalidierung
    max_chars = 100 * 1024 if data.format == "json" else 50 * 1024
    if not data.content:
        raise HTTPException(status_code=422, detail="content darf nicht leer sein")
    if len(data.content.encode("utf-8")) > max_chars:
        raise HTTPException(
            status_code=422,
            detail=f"content zu gross: max {max_chars // 1024}KB fuer format='{data.format}'",
        )

    # JSON parsen wenn format=json
    if data.format == "json":
        try:
            content_parsed = json.loads(data.content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail=f"Ungueliges JSON: {exc}") from exc
    else:
        content_parsed = data.content

    # Celery-Task dispatchen
    from tasks.setup_pipeline_task import run_setup_pipeline

    source = "md_upload" if data.format == "md" else "json_upload"
    payload: dict[str, Any] = {"content": content_parsed, "type": data.type}
    if project_id is not None:
        payload["project_id"] = project_id
    result = run_setup_pipeline.delay(
        str(tenant_id),
        source,
        payload,
    )

    return {"task_id": result.id, "status": "queued"}


# ---------------------------------------------------------------------------
# POST /brand-voice/import-source
# ---------------------------------------------------------------------------


@router.post("/brand-voice/import-source", status_code=202)
async def import_source(
    data: ImportSourceRequest,
    project_id: str | None = Query(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Nextcloud-Import starten."""
    _check_rate_limit(x_api_key)

    if not data.path:
        raise HTTPException(status_code=422, detail="path darf nicht leer sein")

    from tasks.setup_pipeline_task import run_setup_pipeline

    payload: dict[str, Any] = {"path": data.path, "type": data.type}
    if project_id is not None:
        payload["project_id"] = project_id
    result = run_setup_pipeline.delay(
        str(tenant_id),
        "nc_import",
        payload,
    )

    return {"task_id": result.id}


# ---------------------------------------------------------------------------
# POST /brand-voice/regenerate
# ---------------------------------------------------------------------------


@router.post("/brand-voice/regenerate", status_code=202)
async def regenerate(
    data: RegenerateRequest,
    project_id: str | None = Query(None),
    x_api_key: str = Header(..., alias="X-API-Key"),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Transcript-basierte Regenerierung aller Profile."""
    _check_rate_limit(x_api_key)

    from tasks.setup_pipeline_task import run_setup_pipeline

    sources_payload: dict[str, Any] = dict(data.sources)
    if project_id is not None:
        sources_payload["project_id"] = project_id
    result = run_setup_pipeline.delay(
        str(tenant_id),
        "transcript",
        sources_payload,
    )

    return {"task_id": result.id}


# ---------------------------------------------------------------------------
# GET /brand-voice/pipeline/{run_id}  — muss VOR /{tenant_id} definiert sein
# GET /brand-voice/drift-observations — muss VOR /{tenant_id} definiert sein
# ---------------------------------------------------------------------------


@router.get("/brand-voice/pipeline/{run_id}")
async def get_pipeline_run(
    run_id: str,
    tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Setup-Pipeline-Run-Status abrufen."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="run_id muss eine gueltige UUID sein")

    row = (
        await db.execute(
            text(
                "SELECT id, stage, status, input_tokens, output_tokens, "
                "cost_usd, duration_ms, error_meta, created_at, finished_at "
                "FROM setup_pipeline_run WHERE id = :id AND tenant_id = :t"
            ),
            {"id": str(run_uuid), "t": str(tenant_id)},
        )
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Pipeline-Run nicht gefunden")

    error_detail = None
    if row.error_meta and isinstance(row.error_meta, dict):
        error_detail = row.error_meta.get("error")

    return {
        "run_id": str(row.id),
        "status": row.status,
        "stage": row.stage,
        "cost_usd": float(row.cost_usd) if row.cost_usd is not None else None,
        "duration_ms": row.duration_ms,
        "error": error_detail,
    }


# ---------------------------------------------------------------------------
# GET /brand-voice/drift-observations  — muss VOR /{tenant_id} definiert sein
# ---------------------------------------------------------------------------


@router.get("/brand-voice/drift-observations")
async def get_drift_observations(
    tenant_id: str = "me",
    status: str = "pending_review",
    auth_tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Drift-Beobachtungen fuer einen Tenant abrufen (gefiltert nach Status)."""
    resolved_tenant_id = str(auth_tenant_id) if tenant_id == "me" else tenant_id
    if resolved_tenant_id != str(auth_tenant_id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    rows = (
        await db.execute(
            text(
                "SELECT id, tenant_id, trigger_post_ids, current_voice_version, "
                "suggested_changes, status, user_feedback, created_at "
                "FROM voice_drift_observation "
                "WHERE tenant_id = :tenant_id AND status = :status "
                "ORDER BY created_at DESC"
            ),
            {"tenant_id": resolved_tenant_id, "status": status},
        )
    ).fetchall()

    observations = [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "trigger_post_ids": row.trigger_post_ids,
            "current_voice_version": row.current_voice_version,
            "suggested_changes": row.suggested_changes,
            "status": row.status,
            "user_feedback": row.user_feedback,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]

    return {"observations": observations}


# ---------------------------------------------------------------------------
# GET  /brand-voice/review-queue        — muss VOR /{tenant_id} definiert sein
# POST /brand-voice/review-queue/{id}/decide
# ---------------------------------------------------------------------------


class ReviewDecideRequest(BaseModel):
    action: Literal["approved", "rejected"]
    note: str = ""


@router.get("/brand-voice/review-queue")
async def get_review_queue(
    tenant_id: str = "me",
    status: str = "pending",
    auth_tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Sensible Posts in der Review-Queue abrufen (gefiltert nach Status)."""
    # Always use auth tenant — foreign tenant_id query params are silently ignored
    resolved_tenant_id = str(auth_tenant_id)

    rows = (
        await db.execute(
            text(
                "SELECT id, tenant_id, content_piece_id, post_text, severity, "
                "categories, flagged_phrases, confidence, detection_layer, "
                "status, reviewed_by, review_note, created_at, reviewed_at "
                "FROM tenant_review_queue "
                "WHERE tenant_id = :tenant_id AND status = :status "
                "ORDER BY created_at DESC"
            ),
            {"tenant_id": resolved_tenant_id, "status": status},
        )
    ).fetchall()

    items = [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "content_piece_id": str(row.content_piece_id) if row.content_piece_id else None,
            "post_text": row.post_text,
            "severity": row.severity,
            "categories": row.categories,
            "flagged_phrases": row.flagged_phrases,
            "confidence": float(row.confidence) if row.confidence is not None else None,
            "detection_layer": row.detection_layer,
            "status": row.status,
            "reviewed_by": row.reviewed_by,
            "review_note": row.review_note,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        }
        for row in rows
    ]

    return {"items": items, "count": len(items)}


@router.post("/brand-voice/review-queue/{queue_id}/decide")
async def decide_review_queue(
    queue_id: str,
    data: ReviewDecideRequest,
    auth_tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Review-Entscheidung für einen geflaggten Post: approved oder rejected."""
    import uuid as _uuid_mod

    try:
        _uuid_mod.UUID(queue_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Ungültige queue_id — muss UUID-Format sein")

    # 1. Queue-Eintrag laden
    queue_row = (
        await db.execute(
            text(
                "SELECT id, tenant_id, content_piece_id, status "
                "FROM tenant_review_queue WHERE id = :id"
            ),
            {"id": queue_id},
        )
    ).fetchone()

    if not queue_row:
        raise HTTPException(status_code=404, detail="Queue-Eintrag nicht gefunden")

    # Tenant-Isolation
    if str(queue_row.tenant_id) != str(auth_tenant_id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    if queue_row.status != "pending":
        raise HTTPException(status_code=400, detail="Bereits entschieden")

    if data.action not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="action muss 'approved' oder 'rejected' sein")

    # 2. Queue-Eintrag aktualisieren
    await db.execute(
        text(
            "UPDATE tenant_review_queue "
            "SET status = :status, review_note = :note, reviewed_at = NOW() "
            "WHERE id = :id"
        ),
        {"status": data.action, "note": data.note or None, "id": queue_id},
    )

    # 3. Content-Piece-Status synchronisieren
    if queue_row.content_piece_id:
        new_piece_status = "draft" if data.action == "approved" else "rejected"
        await db.execute(
            text(
                "UPDATE content_pieces SET status = :status " "WHERE id = :id AND tenant_id = :tid"
            ),
            {
                "status": new_piece_status,
                "id": str(queue_row.content_piece_id),
                "tid": str(auth_tenant_id),
            },
        )

    await db.commit()

    return {"status": data.action, "queue_id": queue_id}


# ---------------------------------------------------------------------------
# GET /brand-voice/{tenant_id}
# ---------------------------------------------------------------------------


async def _fetch_active_and_history(
    db: AsyncSession,
    profile_type: str,
    tenant_id_str: str,
    project_id: str | None = None,
) -> tuple[dict | None, list[dict]]:
    """Aktive Version und die letzten 10 Eintraege aus einer Profil-Tabelle laden."""
    tbl = _PROFILE_TABLE[profile_type]

    if project_id is None:
        active_sql = (
            f"SELECT id, payload, version, created_at, source FROM {tbl} "
            f"WHERE tenant_id = :t AND project_id IS NULL AND is_active = true"
        )
        history_sql = (
            f"SELECT version, created_at, source FROM {tbl} "
            f"WHERE tenant_id = :t AND project_id IS NULL ORDER BY version DESC LIMIT 10"
        )
        params_active = {"t": tenant_id_str}
        params_history = {"t": tenant_id_str}
    else:
        active_sql = (
            f"SELECT id, payload, version, created_at, source FROM {tbl} "
            f"WHERE tenant_id = :t AND project_id = :pid AND is_active = true"
        )
        history_sql = (
            f"SELECT version, created_at, source FROM {tbl} "
            f"WHERE tenant_id = :t AND project_id = :pid ORDER BY version DESC LIMIT 10"
        )
        params_active = {"t": tenant_id_str, "pid": project_id}
        params_history = {"t": tenant_id_str, "pid": project_id}

    active_row = (await db.execute(text(active_sql), params_active)).fetchone()

    history_rows = (await db.execute(text(history_sql), params_history)).fetchall()

    active = None
    if active_row:
        active = {
            "payload": active_row.payload,
            "version": active_row.version,
            "created_at": active_row.created_at.isoformat() if active_row.created_at else None,
            "source": active_row.source,
        }

    history = [
        {
            "version": r.version,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "source": r.source,
        }
        for r in history_rows
    ]

    return active, history


@router.get("/brand-voice/{tenant_id}")
async def get_brand_voice(
    tenant_id: str,
    project_id: str | None = Query(None),
    auth_tenant=Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Aktive Versionen aller drei Profile + kompakte History."""
    # Resolve 'me' shorthand
    resolved_id = str(auth_tenant.id) if tenant_id == "me" else tenant_id
    # Nur eigene Daten abrufbar (Tenant-Isolation)
    if resolved_id != str(auth_tenant.id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    cc_active, cc_history = await _fetch_active_and_history(
        db, "customer_context", resolved_id, project_id
    )
    vp_active, vp_history = await _fetch_active_and_history(
        db, "voice_profile", resolved_id, project_id
    )
    aa_active, aa_history = await _fetch_active_and_history(
        db, "audience_avatar", resolved_id, project_id
    )

    return {
        "tenant_name": auth_tenant.name,
        "customer_context": cc_active,
        "voice_profile": vp_active,
        "audience_avatar": aa_active,
        "history": {
            "customer_context": cc_history,
            "voice_profile": vp_history,
            "audience_avatar": aa_history,
        },
    }


# ---------------------------------------------------------------------------
# PATCH /brand-voice/{tenant_id}/{profile_type}/field
# ---------------------------------------------------------------------------


@router.patch("/brand-voice/{tenant_id}/{profile_type}/field")
async def patch_profile_field(
    tenant_id: str,
    profile_type: str,
    data: FieldEditRequest,
    project_id: str | None = Query(
        None, description="Projekt-ID für project-scoped Profile (None = globaler Slot)"
    ),
    auth_tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Einzelnes Feld im aktiven Profil editieren (neue Version wird angelegt).

    Mit project_id-Query-Parameter wird das Profil des jeweiligen Projekts
    editiert. Ohne project_id wird der globale Tenant-Slot bearbeitet.
    """
    # Auth check first — must happen before any feature-flag guard
    resolved_id = str(auth_tenant_id) if tenant_id == "me" else tenant_id
    if resolved_id != str(auth_tenant_id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")
    tenant_id = resolved_id

    # Schutzschritt (2026-06-12, #29): Der Dot-Path-Feld-Editor kann kanonische
    # Pflicht-Objekte (z.B. grundton) und minItems-Arrays zerstören und schreibt
    # ohne kanonische Re-Validierung (kein finalize_canonical, escapt HTML, kopiert
    # veraltetes _meta). Bis ein Dokument-Editor (PUT + validate_canonical) bzw. der
    # P17-Update-Pfad steht, ist Feld-Editing deaktiviert. Profil-Korrektur via
    # Re-Run: POST /brand-voice/regenerate. Override: BRAND_VOICE_FIELD_EDIT_ENABLED=1.
    import os as _os

    if _os.environ.get("BRAND_VOICE_FIELD_EDIT_ENABLED", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        raise HTTPException(
            status_code=410,
            detail="Feld-Editor deaktiviert (Schutz kanonischer Louis-Profile, #29). "
            "Bitte Profil neu generieren statt einzelne Felder zu patchen.",
        )

    if profile_type not in _PROFILE_TABLE:
        raise HTTPException(
            status_code=422,
            detail=f"Unbekannter profile_type '{profile_type}'. "
            f"Erlaubt: {list(_PROFILE_TABLE.keys())}",
        )

    # Root-Key aus field_path extrahieren und gegen Allow-List pruefen
    root_key = data.field_path.split(".")[0]
    allowed_keys = EDITABLE_ROOT_KEYS.get(profile_type, [])
    if root_key not in allowed_keys:
        raise HTTPException(
            status_code=422,
            detail=f"Feld '{root_key}' nicht editierbar fuer '{profile_type}'. "
            f"Erlaubte Root-Keys: {allowed_keys}",
        )

    tbl = _PROFILE_TABLE[profile_type]
    # Project-scoped SELECT: COALESCE-Sentinel-Pattern aus Migration 032
    if project_id:
        select_sql = (
            f"SELECT id, payload, version FROM {tbl} "
            f"WHERE tenant_id = :t AND project_id = :pid AND is_active = true"
        )
        select_params: dict = {"t": tenant_id, "pid": project_id}
    else:
        select_sql = (
            f"SELECT id, payload, version FROM {tbl} "
            f"WHERE tenant_id = :t AND project_id IS NULL AND is_active = true"
        )
        select_params = {"t": tenant_id}

    active_row = (await db.execute(text(select_sql), select_params)).fetchone()

    if not active_row:
        raise HTTPException(
            status_code=404,
            detail=f"Kein aktives {profile_type} fuer diesen Tenant"
            + (f" (Projekt {project_id})" if project_id else "")
            + " gefunden",
        )

    # Deep-Copy, Feld setzen
    new_payload = copy.deepcopy(active_row.payload)
    sanitized_value = _sanitize_value(data.new_value)
    try:
        _set_nested(new_payload, data.field_path, sanitized_value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    new_version = active_row.version + 1
    old_id = str(active_row.id)

    # Neue Version inserieren (project_id-aware), alte deaktivieren
    if project_id:
        insert_sql = (
            f"INSERT INTO {tbl} (tenant_id, project_id, version, is_active, source, payload, "
            f"prompt_version_hash, model_id) "
            f"VALUES (:tenant_id, :project_id, :version, true, 'manual_edit', CAST(:payload AS jsonb), '', '')"
        )
        insert_params: dict = {
            "tenant_id": tenant_id,
            "project_id": project_id,
            "version": new_version,
            "payload": json.dumps(new_payload),
        }
    else:
        insert_sql = (
            f"INSERT INTO {tbl} (tenant_id, version, is_active, source, payload, "
            f"prompt_version_hash, model_id) "
            f"VALUES (:tenant_id, :version, true, 'manual_edit', CAST(:payload AS jsonb), '', '')"
        )
        insert_params = {
            "tenant_id": tenant_id,
            "version": new_version,
            "payload": json.dumps(new_payload),
        }

    await db.execute(text(insert_sql), insert_params)
    await db.execute(
        text(_SQL[profile_type]["deactivate"]),
        {"id": old_id},
    )
    await db.commit()

    return {
        "status": "updated",
        "profile_type": profile_type,
        "field_path": data.field_path,
        "new_version": new_version,
        "project_id": project_id,
    }


# ---------------------------------------------------------------------------
# Request-Modelle fuer Drift-Review (Issue #78)
# ---------------------------------------------------------------------------


class DriftChange(BaseModel):
    field_path: str
    accepted: bool
    modified_value: Any = None
    op: str = "set"  # "set" (default, bestehend) | "append" (neu, #43 Schritt 4)


class DriftDecideRequest(BaseModel):
    changes: list[DriftChange]


# ---------------------------------------------------------------------------
# POST /brand-voice/drift-observations/{observation_id}/decide
# ---------------------------------------------------------------------------


@router.post("/brand-voice/drift-observations/{observation_id}/decide")
async def decide_drift_observation(
    observation_id: str,
    data: DriftDecideRequest,
    auth_tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """Drift-Entscheidung: Vorgeschlagene Aenderungen akzeptieren oder ablehnen."""
    # 1. Observation laden
    obs_row = (
        await db.execute(
            text(
                "SELECT id, tenant_id, suggested_changes, current_voice_version, status, "
                "COALESCE(entity_type, 'voice') AS entity_type "
                "FROM voice_drift_observation "
                "WHERE id = :id"
            ),
            {"id": observation_id},
        )
    ).fetchone()

    if not obs_row:
        raise HTTPException(status_code=404, detail="Observation nicht gefunden")

    # Tenant-Isolation
    if str(obs_row.tenant_id) != str(auth_tenant_id):
        raise HTTPException(status_code=403, detail="Zugriff verweigert")

    # 2. Status pruefen
    if obs_row.status != "pending_review":
        raise HTTPException(status_code=400, detail="Already decided")

    if not data.changes:
        raise HTTPException(status_code=422, detail="changes darf nicht leer sein")

    # 3. Accepted / rejected zaehlen
    accepted_count = sum(1 for c in data.changes if c.accepted)
    rejected_count = sum(1 for c in data.changes if not c.accepted)

    if accepted_count == 0:
        new_status = "rejected"
    elif rejected_count == 0:
        new_status = "accepted"
    else:
        new_status = "partial"

    new_version_number = None

    # 4. Fuer accepted/partial: neue Profil-Version anlegen (entitäts-generisch, #43 Schritt 4)
    if new_status in ("accepted", "partial"):
        # Zieltabelle aus entity_type der Observation ableiten (Default 'voice' → Rückwärtskompatibilität)
        entity_type: str = getattr(obs_row, "entity_type", None) or "voice"
        try:
            target_table = get_entity_table(entity_type)
        except ValueError:
            # Unbekannter entity_type → 422. Schutz gegen ungültige DB-Werte.
            raise HTTPException(
                status_code=422,
                detail=f"Unbekannter entity_type in Observation: {entity_type!r}",
            )

        # source-Wert: 'drift_update' für voice (Rückwärtskompatibilität), 'p17_update' für andere
        drift_source = "drift_update" if entity_type == "voice" else "p17_update"

        active_vp_row = (
            await db.execute(
                text(
                    f"SELECT id, payload, version FROM {target_table} "
                    "WHERE tenant_id = :t AND is_active = true"
                ),
                {"t": str(auth_tenant_id)},
            )
        ).fetchone()

        if active_vp_row:
            # suggested_changes als Lookup aufbauen: field_path -> new_value
            suggested_lookup: dict[str, Any] = {}
            if obs_row.suggested_changes and isinstance(obs_row.suggested_changes, list):
                for sc in obs_row.suggested_changes:
                    if isinstance(sc, dict) and "field_path" in sc:
                        suggested_lookup[sc["field_path"]] = sc.get("new_value")

            # Akzeptierte Änderungen als Dict-Liste für den Helper aufbereiten
            accepted_changes = [
                {
                    "field_path": change.field_path,
                    "op": change.op,
                    "new_value": change.modified_value,
                }
                for change in data.changes
                if change.accepted
            ]

            try:
                new_payload = apply_drift_changes(
                    active_vp_row.payload, accepted_changes, suggested_lookup
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

            new_version_number = active_vp_row.version + 1
            old_vp_id = str(active_vp_row.id)

            await db.execute(
                text(
                    f"INSERT INTO {target_table} "
                    "(tenant_id, version, is_active, source, source_meta, payload, "
                    "prompt_version_hash, model_id) "
                    "VALUES (:tenant_id, :version, true, :drift_source, "
                    "CAST(:source_meta AS jsonb), CAST(:payload AS jsonb), '', '')"
                ),
                {
                    "tenant_id": str(auth_tenant_id),
                    "version": new_version_number,
                    "drift_source": drift_source,
                    "source_meta": json.dumps({"observation_id": observation_id}),
                    "payload": json.dumps(new_payload),
                },
            )
            await db.execute(
                text(f"UPDATE {target_table} SET is_active = false WHERE id = :id"),
                {"id": old_vp_id},
            )

    # 5. Observation aktualisieren
    user_feedback = [
        {
            "field_path": c.field_path,
            "accepted": c.accepted,
            "modified_value": c.modified_value,
        }
        for c in data.changes
    ]

    await db.execute(
        text(
            "UPDATE voice_drift_observation "
            "SET status = :status, user_feedback = CAST(:user_feedback AS jsonb) "
            "WHERE id = :id"
        ),
        {
            "status": new_status,
            "user_feedback": json.dumps(user_feedback),
            "id": observation_id,
        },
    )
    await db.commit()

    # 6. Antwort
    return {"status": new_status, "new_version": new_version_number}


# ---------------------------------------------------------------------------
# POST /brand-voice/{tenant_id}/telegram/link
# ---------------------------------------------------------------------------


@router.post("/brand-voice/{tenant_id}/telegram/link")
async def generate_telegram_link(
    tenant_id: uuid.UUID,
    x_api_key: str = Header(..., alias="X-API-Key"),
    auth_tenant_id: uuid.UUID = Depends(get_tenant_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a one-time deeplink token to connect a Telegram user to this tenant.
    The token is valid for 30 minutes.
    """
    if tenant_id != auth_tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden: tenant mismatch")

    token = _secrets.token_urlsafe(24)
    tid = str(tenant_id)

    # UPSERT: telegram_user_id=0 is a placeholder for pending (no user yet).
    # The PK is (tenant_id, telegram_user_id), so a pending slot always has uid=0.
    await db.execute(
        text(
            "INSERT INTO tenant_telegram_link "
            "(tenant_id, telegram_user_id, telegram_chat_id, confirmed_via_token, status, linked_at) "
            "VALUES (:tid, 0, 0, :token, 'pending', now()) "
            "ON CONFLICT (tenant_id, telegram_user_id) DO UPDATE SET "
            "  confirmed_via_token = :token, "
            "  status = 'pending', "
            "  linked_at = now()"
        ),
        {"tid": tid, "token": token},
    )
    await db.commit()

    from config import settings as _settings

    bot_username = _settings.telegram_bot_username or "content_autopilot_bot"

    return {
        "token": token,
        "deeplink": f"https://t.me/{bot_username}?start={token}",
        "expires_in_minutes": 30,
    }
