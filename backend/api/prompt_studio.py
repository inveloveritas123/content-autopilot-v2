"""
Prompt-Studio API (P3).

Endpunkte zum Lesen, Validieren, Speichern und Reverten von content-truth-
Dateien ueber ein beschreibbares Overlay (Overlay-first-Semantik).

Der :ro-Mount von content-truth bleibt unangetastet — Schreibzugriff erfolgt
ausschliesslich ueber das Overlay-Verzeichnis (./data/prompts-custom/).

Löst Issue #23.

Endpunkte:
  GET    /api/prompt-studio/files
  GET    /api/prompt-studio/files/{file_path}
  POST   /api/prompt-studio/files/{file_path}/validate
  PUT    /api/prompt-studio/files/{file_path}
  DELETE /api/prompt-studio/files/{file_path}/overlay
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import settings
from dependencies import get_tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompt-studio")

# ---------------------------------------------------------------------------
# Sicherheit: Pfad-Whitelist
# ---------------------------------------------------------------------------

_ALLOWED_PATH = re.compile(r"^(prompts|rules|schemas)/[A-Za-z0-9._\-]+\.(md|json)$")

# Maximale Dateigroesse (512 KB)
_MAX_SIZE = 512_000


def _check_path(file_path: str) -> str:
    """Validiert den Pfad gegen die Whitelist.

    Erlaubt: genau eine Verzeichnisebene unter prompts/, rules/, schemas/;
    Dateiname-Charset ohne '/', ohne '..'; Endung .md oder .json.
    """
    if ".." in file_path or not _ALLOWED_PATH.fullmatch(file_path):
        raise HTTPException(status_code=400, detail="Pfad nicht erlaubt")
    return file_path


def _kind_from_path(file_path: str) -> Literal["prompt", "rule", "schema"]:
    """Leitet den Kind-Wert aus dem Top-Level-Verzeichnis ab."""
    top = file_path.split("/")[0]
    return {
        "prompts": "prompt",
        "rules": "rule",
        "schemas": "schema",
    }[top]


# ---------------------------------------------------------------------------
# Reverse-Lookup: Pfad → Prompt-Key
# ---------------------------------------------------------------------------


def _build_reverse_map() -> dict[str, str]:
    """Baut eine Reverse-Map PROMPT_PATHS: Pfad → Schluessel."""
    from services.prompt_loader import PROMPT_PATHS

    return {v: k for k, v in PROMPT_PATHS.items()}


# ---------------------------------------------------------------------------
# Adapter-Factory (wird im Test ueberschrieben)
# ---------------------------------------------------------------------------


def get_studio_adapter():
    """Liefert den konfigurierten LayeredStorageAdapter.

    Wird als separate Funktion bereitgestellt damit der Test die Factory
    einfach per dependency_overrides austauschen kann.
    """
    from services.layered_storage import LayeredStorageAdapter
    from services.local_fs_storage import LocalFsStorageAdapter

    base_dir = getattr(settings, "content_truth_base_path", "/app/content-truth")
    overlay_dir = getattr(settings, "content_truth_overlay_path", "/app/data/prompts-custom")
    return LayeredStorageAdapter(
        overlay=LocalFsStorageAdapter(base_dir=overlay_dir),
        base=LocalFsStorageAdapter(base_dir=base_dir),
    )


# ---------------------------------------------------------------------------
# Pydantic-Modelle
# ---------------------------------------------------------------------------

Kind = Literal["prompt", "rule", "schema"]
Source = Literal["base", "overlay"]


class PromptHealth(BaseModel):
    """Health-Ergebnis fuer eine Prompt/Rule-Datei."""

    status: Literal["ok", "weird"]
    system_chars: int
    user_chars: int
    fences_balanced: bool
    issues: list[str]


class PromptFileInfo(BaseModel):
    """Metadaten einer einzelnen Datei in der Liste."""

    path: str  # "prompts/P12-post-generierung.md"
    name: str  # "P12-post-generierung.md"
    kind: Kind  # aus Top-Level-Verzeichnis
    prompt_key: str | None  # Reverse-Lookup in PROMPT_PATHS ("P12"), None fuer Schemas
    source: Source  # effektiver Lese-Layer
    has_overlay: bool
    size: int
    mtime: datetime  # des effektiven Layers
    base_mtime: datetime | None  # immer Base-mtime (fuer "Base neuer als Overlay"-Warnung)


class PromptFileListResponse(BaseModel):
    """Antwort fuer GET /files."""

    files: list[PromptFileInfo]
    overlay_path: str  # informativ: settings.content_truth_overlay_path


class PromptFileContentResponse(BaseModel):
    """Antwort fuer GET /files/{path}."""

    path: str
    kind: Kind
    prompt_key: str | None
    source: Source
    has_overlay: bool
    content: str  # raw UTF-8
    sha256: str  # hex, fuer optimistisches Locking
    mtime: datetime
    base_mtime: datetime | None
    system_prompt: str | None  # via _extract_section; None bei .json
    user_prompt: str | None  # via _extract_section; None bei .json
    health: PromptHealth | None  # nur fuer .md; None bei .json / Schemas


class ValidateRequest(BaseModel):
    """Anfrage fuer POST /validate."""

    content: str


class ValidateResponse(BaseModel):
    """Antwort fuer POST /validate (immer 200, auch bei valid=false)."""

    valid: bool
    kind: Kind
    health: PromptHealth | None  # .md: prompt_health-Checks
    schema_errors: list[str]  # .json: Fehler aus json.loads + check_schema


class SaveRequest(BaseModel):
    """Anfrage fuer PUT /files/{path}."""

    content: str
    base_sha256: str | None = None  # sha256 des Stands, den der Client geladen hat


class SaveResponse(BaseModel):
    """Antwort fuer PUT /files/{path}."""

    path: str
    source: Literal["overlay"]
    sha256: str
    mtime: datetime
    validation: ValidateResponse  # Save validiert immer mit


class RevertResponse(BaseModel):
    """Antwort fuer DELETE /files/{path}/overlay."""

    path: str
    reverted: bool  # False wenn kein Overlay existierte (idempotent)
    source: Literal["base"]


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _compute_sha256(data: bytes) -> str:
    """Berechnet den SHA-256-Hash als Hex-String."""
    return hashlib.sha256(data).hexdigest()


def _run_health(content: str, prompt_key: str | None) -> PromptHealth | None:
    """Fuehrt den Health-Check aus und gibt ein PromptHealth-Modell zurueck."""
    from services.prompt_health_core import check_prompt_content

    result = check_prompt_content(content, prompt_key=prompt_key)
    return PromptHealth(
        status=result.status,
        system_chars=result.system_chars,
        user_chars=result.user_chars,
        fences_balanced=result.fences_balanced,
        issues=result.issues,
    )


def _validate_content(content: str, kind: Kind, prompt_key: str | None) -> ValidateResponse:
    """Validiert Dateiinhalt je nach Kind.

    - schema:  JSON parsen + Draft2020-12-Meta-Schema-Pruefung
    - prompt/rule: Prompt-Health-Check
    """
    if kind == "schema":
        schema_errors: list[str] = []
        parsed = None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            schema_errors.append(f"JSON-Parse-Fehler: {exc}")

        if parsed is not None:
            try:
                import jsonschema

                jsonschema.Draft202012Validator.check_schema(parsed)
            except jsonschema.SchemaError as exc:
                schema_errors.append(f"JSON-Schema-Fehler: {exc.message}")
            except Exception as exc:
                schema_errors.append(f"Schema-Pruefung fehlgeschlagen: {exc}")

        return ValidateResponse(
            valid=(len(schema_errors) == 0),
            kind=kind,
            health=None,
            schema_errors=schema_errors,
        )

    # prompt / rule
    health = _run_health(content, prompt_key)
    return ValidateResponse(
        valid=(health.status == "ok"),
        kind=kind,
        health=health,
        schema_errors=[],
    )


def _invalidate_loader_cache(prompt_key: str | None) -> None:
    """Invalidiert den PromptLoader-Cache des API-Prozesses.

    Bei unbekanntem Key oder fehlschlagender Loader-Instanziierung wird
    der Fehler geloggt aber nicht weitergeworfen (Non-critical).
    """
    try:
        from services.prompt_loader import get_default_prompt_loader

        loader = get_default_prompt_loader()
        if prompt_key:
            loader.invalidate(prompt_key)
            logger.debug("prompt_studio: cache invalidiert fuer key=%r", prompt_key)
        else:
            loader.invalidate_all()
            logger.debug("prompt_studio: gesamter cache invalidiert")
    except Exception as exc:
        logger.warning("prompt_studio: cache-invalidierung fehlgeschlagen: %s", exc)


# ---------------------------------------------------------------------------
# Endpunkte
# ---------------------------------------------------------------------------


@router.get("/files", response_model=PromptFileListResponse)
async def list_files(_tenant=Depends(get_tenant)):
    """GET /api/prompt-studio/files — Alle editierbaren Dateien auflisten.

    Quellen: prompts/, rules/, schemas/ aus dem LayeredStorageAdapter.
    Nur Dateien die _ALLOWED_PATH matchen werden zurueckgegeben.
    """
    adapter = get_studio_adapter()
    reverse_map = _build_reverse_map()
    overlay_path = getattr(settings, "content_truth_overlay_path", "/app/data/prompts-custom")

    files: list[PromptFileInfo] = []

    for top_dir in ("prompts", "rules", "schemas"):
        try:
            entries_with_source = adapter.list_with_source(top_dir)
        except Exception:
            continue

        for entry, source, stat in entries_with_source:
            # Pfad normalisieren (fuehrendes '/' entfernen)
            raw_path = entry.path.lstrip("/")
            if not _ALLOWED_PATH.fullmatch(raw_path):
                continue

            kind = _kind_from_path(raw_path)
            prompt_key = reverse_map.get(raw_path)
            has_overlay = source == "overlay"

            # Base-mtime fuer "Base neuer als Overlay"-Warnung
            base_stat = adapter.stat_base(raw_path)
            base_mtime = base_stat.mtime if base_stat else None

            files.append(
                PromptFileInfo(
                    path=raw_path,
                    name=entry.name,
                    kind=kind,
                    prompt_key=prompt_key,
                    source=source,
                    has_overlay=has_overlay,
                    size=stat.size,
                    mtime=stat.mtime,
                    base_mtime=base_mtime,
                )
            )

    return PromptFileListResponse(files=files, overlay_path=overlay_path)


@router.get("/files/{file_path:path}", response_model=PromptFileContentResponse)
async def get_file(file_path: str, _tenant=Depends(get_tenant)):
    """GET /api/prompt-studio/files/{path} — Dateiinhalt lesen.

    Gibt raw UTF-8-Inhalt, sha256, mtime, Health (fuer .md) zurueck.
    """
    _check_path(file_path)
    adapter = get_studio_adapter()
    reverse_map = _build_reverse_map()

    from services.brand_voice_storage import StorageError

    if not adapter.exists(file_path):
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")

    try:
        raw = adapter.read(file_path)
    except StorageError as exc:
        raise HTTPException(status_code=404, detail=f"Datei nicht lesbar: {exc}")

    content = raw.decode("utf-8")
    sha = _compute_sha256(raw)
    stat = adapter.stat(file_path)
    source = adapter.source_of(file_path) or "base"
    has_overlay = source == "overlay"
    kind = _kind_from_path(file_path)
    prompt_key = reverse_map.get(file_path)

    base_stat = adapter.stat_base(file_path)
    base_mtime = base_stat.mtime if base_stat else None

    # Sektionen und Health nur fuer .md-Dateien
    system_prompt: str | None = None
    user_prompt: str | None = None
    health: PromptHealth | None = None

    if file_path.endswith(".md"):
        from services.prompt_loader import _extract_section

        system_prompt = _extract_section(content, "System-Prompt")
        user_prompt = _extract_section(content, "User-Prompt")
        health = _run_health(content, prompt_key)

    return PromptFileContentResponse(
        path=file_path,
        kind=kind,
        prompt_key=prompt_key,
        source=source,  # type: ignore[arg-type]
        has_overlay=has_overlay,
        content=content,
        sha256=sha,
        mtime=stat.mtime,
        base_mtime=base_mtime,
        system_prompt=system_prompt if file_path.endswith(".md") else None,
        user_prompt=user_prompt if file_path.endswith(".md") else None,
        health=health,
    )


@router.post("/files/{file_path:path}/validate", response_model=ValidateResponse)
async def validate_file(
    file_path: str,
    body: ValidateRequest,
    _tenant=Depends(get_tenant),
):
    """POST /api/prompt-studio/files/{path}/validate — Inhalt validieren.

    Validiert den mitgeschickten Content (nicht den gespeicherten),
    damit die UI vor dem Save pruefen kann.
    Gibt immer 200 zurueck, auch bei valid=false.
    """
    _check_path(file_path)

    if len(body.content) > _MAX_SIZE:
        raise HTTPException(status_code=413, detail="Inhalt zu gross (max 512 KB)")

    kind = _kind_from_path(file_path)
    reverse_map = _build_reverse_map()
    prompt_key = reverse_map.get(file_path)

    return _validate_content(body.content, kind, prompt_key)


@router.put("/files/{file_path:path}", response_model=SaveResponse)
async def save_file(
    file_path: str,
    body: SaveRequest,
    tenant=Depends(get_tenant),
):
    """PUT /api/prompt-studio/files/{path} — Datei im Overlay speichern.

    Ablauf:
    1. Whitelist + Groessenlimit + Base-Existenz pruefen
    2. Optimistisches Locking: base_sha256 pruefen
    3. Validierung (harter Block fuer kaputte JSON-Schemas, Warnung fuer .md)
    4. Atomar ins Overlay schreiben
    5. PromptLoader-Cache invalidieren
    6. Audit-Log
    """
    _check_path(file_path)

    if len(body.content) > _MAX_SIZE:
        raise HTTPException(status_code=413, detail="Inhalt zu gross (max 512 KB)")

    adapter = get_studio_adapter()
    reverse_map = _build_reverse_map()
    prompt_key = reverse_map.get(file_path)
    kind = _kind_from_path(file_path)

    from services.brand_voice_storage import StorageError

    # Base-Existenz pruefen (kein Anlegen neuer Dateien in v1)
    if not adapter.stat_base(file_path):
        raise HTTPException(
            status_code=404,
            detail="Datei existiert nicht in der Base — neue Dateien koennen nicht angelegt werden",
        )

    # Optimistisches Locking: sha256 des aktuell effektiven Stands pruefen
    if body.base_sha256 is not None:
        try:
            current_raw = adapter.read(file_path)
        except StorageError:
            current_raw = b""
        current_sha = _compute_sha256(current_raw)
        if current_sha != body.base_sha256:
            raise HTTPException(
                status_code=409,
                detail="Konflikt: Datei wurde zwischenzeitlich geaendert",
            )

    # Validierung
    validation = _validate_content(body.content, kind, prompt_key)

    # Schema-Dateien mit invalidem JSON / Meta-Schema-Fehler: harter Block
    if kind == "schema" and not validation.valid:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Schema-Datei konnte nicht gespeichert werden (ungueltig)",
                "schema_errors": validation.schema_errors,
            },
        )

    # Atomar ins Overlay schreiben
    content_bytes = body.content.encode("utf-8")
    try:
        adapter.write(file_path, content_bytes)
    except StorageError as exc:
        raise HTTPException(status_code=500, detail=f"Schreiben fehlgeschlagen: {exc}")

    # PromptLoader-Cache invalidieren
    _invalidate_loader_cache(prompt_key)

    # Metadaten des neuen Overlay-Stands lesen
    try:
        new_stat = adapter.stat(file_path)
    except StorageError:
        new_stat = None
    new_sha = _compute_sha256(content_bytes)
    mtime = new_stat.mtime if new_stat else datetime.now(UTC)

    # sha256 des vorherigen Stands fuer das Audit-Log
    sha_before = body.base_sha256 or "(unbekannt)"

    # Audit-Log: strukturierte Logzeile
    logger.info(
        "prompt_studio: save",
        extra={
            "path": file_path,
            "tenant_id": str(tenant.id),
            "sha_before": sha_before,
            "sha_after": new_sha,
            "size": len(content_bytes),
        },
    )

    return SaveResponse(
        path=file_path,
        source="overlay",
        sha256=new_sha,
        mtime=mtime,
        validation=validation,
    )


@router.delete("/files/{file_path:path}/overlay", response_model=RevertResponse)
async def revert_file(
    file_path: str,
    tenant=Depends(get_tenant),
):
    """DELETE /api/prompt-studio/files/{path}/overlay — Overlay loeschen (Revert-to-Base).

    Idempotent: 200 mit reverted=false wenn kein Overlay existierte.
    Invalidiert den PromptLoader-Cache wegen der mtime-Rueckwaerts-Falle:
    Base-mtime koennte aelter als Cache-loaded_at sein.
    """
    _check_path(file_path)

    adapter = get_studio_adapter()
    reverse_map = _build_reverse_map()
    prompt_key = reverse_map.get(file_path)

    reverted = adapter.delete_overlay(file_path)

    # Cache immer invalidieren (mtime-Rueckwaerts-Falle nach Revert)
    _invalidate_loader_cache(prompt_key)

    logger.info(
        "prompt_studio: revert",
        extra={
            "path": file_path,
            "tenant_id": str(tenant.id),
            "reverted": reverted,
        },
    )

    return RevertResponse(
        path=file_path,
        reverted=reverted,
        source="base",
    )
