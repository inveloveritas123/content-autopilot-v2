"""
TenantExportService — Baut ZIP-Export mit allen Tenant-Daten.

Sensible Felder werden REDACTED:
- Tenant: api_key, api_key_secondary
- LLMProvider: api_key_encrypted
- Allgemein: alle Felder die *password*, *token*, *secret* im Namen enthalten
"""

import csv
import io
import json
import re
import uuid
import zipfile
from datetime import date, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.campaign import Campaign
from models.carousel import CarouselTemplate
from models.content_dna import ContentDNAProfile
from models.content_idea import ContentIdea
from models.content_performance import ContentPerformance, IdeaSelectionLog
from models.content_piece import ContentPiece
from models.dialogue_question import DialogueQuestion
from models.entrepreneur_answer import EntrepreneurAnswer
from models.llm_call_log import LLMCallLog
from models.llm_provider import LLMProvider
from models.quality_metric import QualityMetric
from models.scheduled_post import ScheduledPost
from models.source import Source
from models.source_item import SourceItem
from models.tenant import Tenant

# Feldnamen-Pattern, die REDACTED werden
_SENSITIVE_PATTERN = re.compile(r"(api_key|password|token|secret)", re.IGNORECASE)

_EXPLICIT_REDACT = {
    # model-class → set of field names
    "Tenant": {"api_key", "api_key_secondary"},
    "LLMProvider": {"api_key_encrypted"},
}


def _serialize_value(v: Any) -> Any:
    """Konvertiert nicht-JSON-serialisierbare Typen."""
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return v


def _serialize_row(obj: Any, model_name: str) -> dict:
    """Serialisiert ein SQLAlchemy-Objekt als dict, redacted sensible Felder."""
    explicit = _EXPLICIT_REDACT.get(model_name, set())
    row = {}
    state = obj.__dict__
    for key, value in state.items():
        if key.startswith("_"):
            continue
        if key in explicit or _SENSITIVE_PATTERN.search(key):
            row[key] = "***REDACTED***"
        else:
            row[key] = _serialize_value(value)
    return row


def _rows_to_json(rows: list, model_name: str) -> str:
    data = [_serialize_row(r, model_name) for r in rows]
    return json.dumps(data, ensure_ascii=False, indent=2)


_README = """\
# Tenant-Daten-Export — Content Autopilot v2

Dieses ZIP enthält alle Daten eines Tenants.

## Dateien

| Datei | Inhalt |
|---|---|
| manifest.json | Metadaten: Version, Datum, Anzahlen |
| tenant.json | Tenant-Stammdaten (api_key REDACTED) |
| sources.json | Quellen (YouTube, RSS, …) |
| source_items.json | Einzelne Items der Quellen |
| content_ideas.json | Generierte Content-Ideen |
| entrepreneur_answers.json | Unternehmer-Antworten auf Fragen |
| content_pieces.json | Fertige Content-Stücke |
| campaigns.json | Kampagnen |
| carousel_templates.json | Karussell-Vorlagen |
| dialogue_questions.json | Smart-Fragen |
| llm_providers.json | LLM-Provider-Konfiguration (api_key_encrypted REDACTED) |
| llm_call_logs.json | Token-Verbrauch und Kosten |
| scheduled_posts.json | Geplante Posts |
| quality_metrics.json | Qualitäts-Metriken |
| content_performances.json | Performance-Tracking |
| idea_selection_logs.json | Ideen-Selektion-Log |
| content_dna_profiles.json | Content-DNA-Profile |

## Import

POST /api/tenants/me/data-import mit dem ZIP als multipart-Upload.
Query-Params: dry_run=true (Vorschau), merge=true (Upsert), confirm=true (Pflicht für echten Import).

## Hinweise

- Sensible Felder sind als "***REDACTED***" markiert
- UUID-Felder sind als Strings serialisiert
- Datetime-Felder sind im ISO-8601-Format
- schema_version: 2.0.0
"""


class TenantExportService:
    async def _get_all_data(self, tenant: Tenant, db: AsyncSession) -> dict:
        """Gemeinsame DB-Abfrage für alle Export-Formate."""
        tid = tenant.id
        sources = (await db.execute(select(Source).where(Source.tenant_id == tid))).scalars().all()
        source_items = (
            (await db.execute(select(SourceItem).where(SourceItem.tenant_id == tid)))
            .scalars()
            .all()
        )
        content_ideas = (
            (await db.execute(select(ContentIdea).where(ContentIdea.tenant_id == tid)))
            .scalars()
            .all()
        )
        entrepreneur_answers = (
            (
                await db.execute(
                    select(EntrepreneurAnswer).where(EntrepreneurAnswer.tenant_id == tid)
                )
            )
            .scalars()
            .all()
        )
        content_pieces = (
            (await db.execute(select(ContentPiece).where(ContentPiece.tenant_id == tid)))
            .scalars()
            .all()
        )
        campaigns = (
            (await db.execute(select(Campaign).where(Campaign.tenant_id == tid))).scalars().all()
        )
        carousel_templates = (
            (await db.execute(select(CarouselTemplate).where(CarouselTemplate.tenant_id == tid)))
            .scalars()
            .all()
        )
        dialogue_questions = (
            (await db.execute(select(DialogueQuestion).where(DialogueQuestion.tenant_id == tid)))
            .scalars()
            .all()
        )
        llm_providers = (
            (await db.execute(select(LLMProvider).where(LLMProvider.tenant_id == tid)))
            .scalars()
            .all()
        )
        llm_call_logs = (
            (await db.execute(select(LLMCallLog).where(LLMCallLog.tenant_id == tid)))
            .scalars()
            .all()
        )
        scheduled_posts = (
            (await db.execute(select(ScheduledPost).where(ScheduledPost.tenant_id == tid)))
            .scalars()
            .all()
        )
        quality_metrics = (
            (await db.execute(select(QualityMetric).where(QualityMetric.tenant_id == tid)))
            .scalars()
            .all()
        )
        content_performances = (
            (
                await db.execute(
                    select(ContentPerformance).where(ContentPerformance.tenant_id == tid)
                )
            )
            .scalars()
            .all()
        )
        idea_selection_logs = (
            (await db.execute(select(IdeaSelectionLog).where(IdeaSelectionLog.tenant_id == tid)))
            .scalars()
            .all()
        )
        content_dna_profiles = (
            (await db.execute(select(ContentDNAProfile).where(ContentDNAProfile.tenant_id == tid)))
            .scalars()
            .all()
        )
        return {
            "sources": sources,
            "source_items": source_items,
            "content_ideas": content_ideas,
            "entrepreneur_answers": entrepreneur_answers,
            "content_pieces": content_pieces,
            "campaigns": campaigns,
            "carousel_templates": carousel_templates,
            "dialogue_questions": dialogue_questions,
            "llm_providers": llm_providers,
            "llm_call_logs": llm_call_logs,
            "scheduled_posts": scheduled_posts,
            "quality_metrics": quality_metrics,
            "content_performances": content_performances,
            "idea_selection_logs": idea_selection_logs,
            "content_dna_profiles": content_dna_profiles,
        }

    async def build_export_zip(self, tenant: Tenant, db: AsyncSession) -> bytes:
        """Baut ZIP-File mit allen Tenant-Daten als JSON. Gibt Bytes zurück."""
        data = await self._get_all_data(tenant, db)

        counts = {k: len(v) for k, v in data.items()}
        manifest = {
            "schema_version": "2.0.0",
            "export_date": datetime.utcnow().isoformat(),
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "counts": counts,
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr("README.md", _README)
            zf.writestr("tenant.json", _rows_to_json([tenant], "Tenant"))
            zf.writestr("sources.json", _rows_to_json(data["sources"], "Source"))
            zf.writestr("source_items.json", _rows_to_json(data["source_items"], "SourceItem"))
            zf.writestr("content_ideas.json", _rows_to_json(data["content_ideas"], "ContentIdea"))
            zf.writestr(
                "entrepreneur_answers.json",
                _rows_to_json(data["entrepreneur_answers"], "EntrepreneurAnswer"),
            )
            zf.writestr(
                "content_pieces.json", _rows_to_json(data["content_pieces"], "ContentPiece")
            )
            zf.writestr("campaigns.json", _rows_to_json(data["campaigns"], "Campaign"))
            zf.writestr(
                "carousel_templates.json",
                _rows_to_json(data["carousel_templates"], "CarouselTemplate"),
            )
            zf.writestr(
                "dialogue_questions.json",
                _rows_to_json(data["dialogue_questions"], "DialogueQuestion"),
            )
            zf.writestr("llm_providers.json", _rows_to_json(data["llm_providers"], "LLMProvider"))
            zf.writestr("llm_call_logs.json", _rows_to_json(data["llm_call_logs"], "LLMCallLog"))
            zf.writestr(
                "scheduled_posts.json", _rows_to_json(data["scheduled_posts"], "ScheduledPost")
            )
            zf.writestr(
                "quality_metrics.json", _rows_to_json(data["quality_metrics"], "QualityMetric")
            )
            zf.writestr(
                "content_performances.json",
                _rows_to_json(data["content_performances"], "ContentPerformance"),
            )
            zf.writestr(
                "idea_selection_logs.json",
                _rows_to_json(data["idea_selection_logs"], "IdeaSelectionLog"),
            )
            zf.writestr(
                "content_dna_profiles.json",
                _rows_to_json(data["content_dna_profiles"], "ContentDNAProfile"),
            )

        buf.seek(0)
        return buf.read()

    async def build_export_excel(
        self, tenant: Tenant, db: AsyncSession, data: dict | None = None
    ) -> bytes:
        """Erstellt eine .xlsx-Datei mit je einem Sheet pro Tabelle."""
        if data is None:
            data = await self._get_all_data(tenant, db)
        bold = Font(bold=True)

        wb = Workbook()
        # Erstes (leeres) Default-Sheet entfernen
        wb.remove(wb.active)

        def _add_sheet(sheet_name: str, headers: list, rows_data: list):
            ws = wb.create_sheet(title=sheet_name)
            ws.append(headers)
            for cell in ws[1]:
                cell.font = bold
            for row in rows_data:
                ws.append(row)
            # Spaltenbreiten automatisch setzen (max 60)
            for col_cells in ws.columns:
                max_len = max((len(str(c.value)) if c.value is not None else 0) for c in col_cells)
                ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 2, 62)

        def _dt(val):
            if isinstance(val, datetime | date):
                return val.isoformat()
            return val

        # posts (content_pieces)
        _add_sheet(
            "posts",
            ["id", "status", "category", "title", "created_at"],
            [
                [
                    str(r.id),
                    r.status,
                    getattr(r, "category", None),
                    (r.title or "")[:100] if hasattr(r, "title") else "",
                    _dt(r.created_at),
                ]
                for r in data["content_pieces"]
            ],
        )

        # sources
        _add_sheet(
            "sources",
            ["id", "url", "source_type", "is_active", "created_at"],
            [[str(r.id), r.url, r.type, r.is_active, _dt(r.created_at)] for r in data["sources"]],
        )

        # source_items
        _add_sheet(
            "source_items",
            ["id", "source_id", "title", "published_at", "fetched_at"],
            [
                [
                    str(r.id),
                    str(r.source_id),
                    (r.title or "")[:200] if hasattr(r, "title") else "",
                    _dt(getattr(r, "published_at", None)),
                    _dt(getattr(r, "fetched_at", None)),
                ]
                for r in data["source_items"]
            ],
        )

        # ideas (content_ideas)
        _add_sheet(
            "ideas",
            ["id", "status", "hook", "pillar", "created_at"],
            [
                [
                    str(r.id),
                    r.status,
                    (getattr(r, "hook", None) or "")[:200],
                    getattr(r, "pillar", None),
                    _dt(r.created_at),
                ]
                for r in data["content_ideas"]
            ],
        )

        # dialogue_questions
        _add_sheet(
            "dialogue_questions",
            ["id", "idea_id", "question", "answer"],
            [
                [
                    str(r.id),
                    str(getattr(r, "idea_id", None)),
                    (getattr(r, "question", None) or "")[:200],
                    (getattr(r, "answer", None) or "")[:200],
                ]
                for r in data["dialogue_questions"]
            ],
        )

        # llm_calls (llm_call_logs)
        _add_sheet(
            "llm_calls",
            [
                "id",
                "stage",
                "model_name",
                "input_tokens",
                "output_tokens",
                "cost_usd",
                "created_at",
            ],
            [
                [
                    str(r.id),
                    getattr(r, "stage", None),
                    getattr(r, "model_name", None),
                    getattr(r, "input_tokens", None),
                    getattr(r, "output_tokens", None),
                    getattr(r, "cost_usd", None),
                    _dt(r.created_at),
                ]
                for r in data["llm_call_logs"]
            ],
        )

        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out.read()

    async def build_export_csv_zip(
        self, tenant: Tenant, db: AsyncSession, data: dict | None = None
    ) -> bytes:
        """Erstellt ein ZIP mit einer UTF-8-BOM CSV pro Tabelle."""
        if data is None:
            data = await self._get_all_data(tenant, db)

        def _dt(val):
            if isinstance(val, datetime | date):
                return val.isoformat()
            return val if val is not None else ""

        def _make_csv(headers: list, rows_data: list) -> bytes:
            buf = io.StringIO(initial_value="\ufeff")  # UTF-8-BOM als Initialwert
            writer = csv.writer(buf)
            writer.writerow(headers)
            for row in rows_data:
                writer.writerow([str(v) if v is not None else "" for v in row])
            return buf.getvalue().encode("utf-8")

        sheets = {
            "csv/posts.csv": (
                ["id", "status", "category", "title", "created_at"],
                [
                    [
                        str(r.id),
                        r.status,
                        getattr(r, "category", None),
                        (r.title or "")[:100] if hasattr(r, "title") else "",
                        _dt(r.created_at),
                    ]
                    for r in data["content_pieces"]
                ],
            ),
            "csv/sources.csv": (
                ["id", "url", "source_type", "is_active", "created_at"],
                [
                    [str(r.id), r.url, r.type, r.is_active, _dt(r.created_at)]
                    for r in data["sources"]
                ],
            ),
            "csv/source_items.csv": (
                ["id", "source_id", "title", "published_at", "fetched_at"],
                [
                    [
                        str(r.id),
                        str(r.source_id),
                        (r.title or "")[:200] if hasattr(r, "title") else "",
                        _dt(getattr(r, "published_at", None)),
                        _dt(getattr(r, "fetched_at", None)),
                    ]
                    for r in data["source_items"]
                ],
            ),
            "csv/ideas.csv": (
                ["id", "status", "hook", "pillar", "created_at"],
                [
                    [
                        str(r.id),
                        r.status,
                        (getattr(r, "hook", None) or "")[:200],
                        getattr(r, "pillar", None),
                        _dt(r.created_at),
                    ]
                    for r in data["content_ideas"]
                ],
            ),
            "csv/dialogue_questions.csv": (
                ["id", "idea_id", "question", "answer"],
                [
                    [
                        str(r.id),
                        str(getattr(r, "idea_id", None)),
                        (getattr(r, "question", None) or "")[:200],
                        (getattr(r, "answer", None) or "")[:200],
                    ]
                    for r in data["dialogue_questions"]
                ],
            ),
            "csv/llm_calls.csv": (
                [
                    "id",
                    "stage",
                    "model_name",
                    "input_tokens",
                    "output_tokens",
                    "cost_usd",
                    "created_at",
                ],
                [
                    [
                        str(r.id),
                        getattr(r, "stage", None),
                        getattr(r, "model_name", None),
                        getattr(r, "input_tokens", None),
                        getattr(r, "output_tokens", None),
                        getattr(r, "cost_usd", None),
                        _dt(r.created_at),
                    ]
                    for r in data["llm_call_logs"]
                ],
            ),
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for filename, (headers, rows_data) in sheets.items():
                zf.writestr(filename, _make_csv(headers, rows_data))
        buf.seek(0)
        return buf.read()

    async def build_export_all(self, tenant: Tenant, db: AsyncSession) -> bytes:
        """Baut ein ZIP mit JSON, Excel und CSV kombiniert."""
        data = await self._get_all_data(tenant, db)

        # JSON-Inhalt (aus build_export_zip übernommen, ohne erneuten DB-Aufruf)
        counts = {k: len(v) for k, v in data.items()}
        manifest = {
            "schema_version": "2.0.0",
            "export_date": datetime.utcnow().isoformat(),
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.name,
            "formats": ["json", "excel", "csv"],
            "counts": counts,
        }

        # Daten einmal geladen, weiterreichen — kein extra DB-Aufruf
        excel_bytes = await self.build_export_excel(tenant, db, data=data)
        csv_zip_bytes = await self.build_export_csv_zip(tenant, db, data=data)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr("README.md", _README)
            # JSON-Dateien
            zf.writestr("json/tenant.json", _rows_to_json([tenant], "Tenant"))
            zf.writestr("json/sources.json", _rows_to_json(data["sources"], "Source"))
            zf.writestr("json/source_items.json", _rows_to_json(data["source_items"], "SourceItem"))
            zf.writestr(
                "json/content_ideas.json", _rows_to_json(data["content_ideas"], "ContentIdea")
            )
            zf.writestr(
                "json/entrepreneur_answers.json",
                _rows_to_json(data["entrepreneur_answers"], "EntrepreneurAnswer"),
            )
            zf.writestr(
                "json/content_pieces.json", _rows_to_json(data["content_pieces"], "ContentPiece")
            )
            zf.writestr("json/campaigns.json", _rows_to_json(data["campaigns"], "Campaign"))
            zf.writestr(
                "json/carousel_templates.json",
                _rows_to_json(data["carousel_templates"], "CarouselTemplate"),
            )
            zf.writestr(
                "json/dialogue_questions.json",
                _rows_to_json(data["dialogue_questions"], "DialogueQuestion"),
            )
            zf.writestr(
                "json/llm_providers.json", _rows_to_json(data["llm_providers"], "LLMProvider")
            )
            zf.writestr(
                "json/llm_call_logs.json", _rows_to_json(data["llm_call_logs"], "LLMCallLog")
            )
            zf.writestr(
                "json/scheduled_posts.json", _rows_to_json(data["scheduled_posts"], "ScheduledPost")
            )
            zf.writestr(
                "json/quality_metrics.json", _rows_to_json(data["quality_metrics"], "QualityMetric")
            )
            zf.writestr(
                "json/content_performances.json",
                _rows_to_json(data["content_performances"], "ContentPerformance"),
            )
            zf.writestr(
                "json/idea_selection_logs.json",
                _rows_to_json(data["idea_selection_logs"], "IdeaSelectionLog"),
            )
            zf.writestr(
                "json/content_dna_profiles.json",
                _rows_to_json(data["content_dna_profiles"], "ContentDNAProfile"),
            )
            # Excel
            zf.writestr("excel/export.xlsx", excel_bytes)
            # CSV (CSV-ZIP entpacken und Einträge übertragen)
            with zipfile.ZipFile(io.BytesIO(csv_zip_bytes)) as csv_zf:
                for name in csv_zf.namelist():
                    zf.writestr(name, csv_zf.read(name))

        buf.seek(0)
        return buf.read()
