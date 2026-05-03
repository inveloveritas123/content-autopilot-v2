"""
TenantExportService — Baut ZIP-Export mit allen Tenant-Daten.

Sensible Felder werden REDACTED:
- Tenant: api_key, api_key_secondary
- LLMProvider: api_key_encrypted
- Allgemein: alle Felder die *password*, *token*, *secret* im Namen enthalten
"""
import io
import json
import re
import uuid
import zipfile
from datetime import date, datetime
from typing import Any

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
_SENSITIVE_PATTERN = re.compile(
    r"(api_key|password|token|secret)", re.IGNORECASE
)

_EXPLICIT_REDACT = {
    # model-class → set of field names
    "Tenant": {"api_key", "api_key_secondary"},
    "LLMProvider": {"api_key_encrypted"},
}


def _serialize_value(v: Any) -> Any:
    """Konvertiert nicht-JSON-serialisierbare Typen."""
    if isinstance(v, (uuid.UUID,)):
        return str(v)
    if isinstance(v, (datetime,)):
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
    async def build_export_zip(self, tenant: Tenant, db: AsyncSession) -> bytes:
        """Baut ZIP-File mit allen Tenant-Daten. Gibt Bytes zurück."""
        tid = tenant.id

        # Alle Tabellen abfragen
        sources = (await db.execute(select(Source).where(Source.tenant_id == tid))).scalars().all()
        source_items = (await db.execute(select(SourceItem).where(SourceItem.tenant_id == tid))).scalars().all()
        content_ideas = (await db.execute(select(ContentIdea).where(ContentIdea.tenant_id == tid))).scalars().all()
        entrepreneur_answers = (await db.execute(select(EntrepreneurAnswer).where(EntrepreneurAnswer.tenant_id == tid))).scalars().all()
        content_pieces = (await db.execute(select(ContentPiece).where(ContentPiece.tenant_id == tid))).scalars().all()
        campaigns = (await db.execute(select(Campaign).where(Campaign.tenant_id == tid))).scalars().all()
        carousel_templates = (await db.execute(select(CarouselTemplate).where(CarouselTemplate.tenant_id == tid))).scalars().all()
        dialogue_questions = (await db.execute(select(DialogueQuestion).where(DialogueQuestion.tenant_id == tid))).scalars().all()
        llm_providers = (await db.execute(select(LLMProvider).where(LLMProvider.tenant_id == tid))).scalars().all()
        llm_call_logs = (await db.execute(select(LLMCallLog).where(LLMCallLog.tenant_id == tid))).scalars().all()
        scheduled_posts = (await db.execute(select(ScheduledPost).where(ScheduledPost.tenant_id == tid))).scalars().all()
        quality_metrics = (await db.execute(select(QualityMetric).where(QualityMetric.tenant_id == tid))).scalars().all()
        content_performances = (await db.execute(select(ContentPerformance).where(ContentPerformance.tenant_id == tid))).scalars().all()
        idea_selection_logs = (await db.execute(select(IdeaSelectionLog).where(IdeaSelectionLog.tenant_id == tid))).scalars().all()
        content_dna_profiles = (await db.execute(select(ContentDNAProfile).where(ContentDNAProfile.tenant_id == tid))).scalars().all()

        counts = {
            "sources": len(sources),
            "source_items": len(source_items),
            "content_ideas": len(content_ideas),
            "entrepreneur_answers": len(entrepreneur_answers),
            "content_pieces": len(content_pieces),
            "campaigns": len(campaigns),
            "carousel_templates": len(carousel_templates),
            "dialogue_questions": len(dialogue_questions),
            "llm_providers": len(llm_providers),
            "llm_call_logs": len(llm_call_logs),
            "scheduled_posts": len(scheduled_posts),
            "quality_metrics": len(quality_metrics),
            "content_performances": len(content_performances),
            "idea_selection_logs": len(idea_selection_logs),
            "content_dna_profiles": len(content_dna_profiles),
        }

        manifest = {
            "schema_version": "2.0.0",
            "export_date": datetime.utcnow().isoformat(),
            "tenant_id": str(tid),
            "tenant_name": tenant.name,
            "counts": counts,
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr("README.md", _README)
            zf.writestr("tenant.json", _rows_to_json([tenant], "Tenant"))
            zf.writestr("sources.json", _rows_to_json(sources, "Source"))
            zf.writestr("source_items.json", _rows_to_json(source_items, "SourceItem"))
            zf.writestr("content_ideas.json", _rows_to_json(content_ideas, "ContentIdea"))
            zf.writestr("entrepreneur_answers.json", _rows_to_json(entrepreneur_answers, "EntrepreneurAnswer"))
            zf.writestr("content_pieces.json", _rows_to_json(content_pieces, "ContentPiece"))
            zf.writestr("campaigns.json", _rows_to_json(campaigns, "Campaign"))
            zf.writestr("carousel_templates.json", _rows_to_json(carousel_templates, "CarouselTemplate"))
            zf.writestr("dialogue_questions.json", _rows_to_json(dialogue_questions, "DialogueQuestion"))
            zf.writestr("llm_providers.json", _rows_to_json(llm_providers, "LLMProvider"))
            zf.writestr("llm_call_logs.json", _rows_to_json(llm_call_logs, "LLMCallLog"))
            zf.writestr("scheduled_posts.json", _rows_to_json(scheduled_posts, "ScheduledPost"))
            zf.writestr("quality_metrics.json", _rows_to_json(quality_metrics, "QualityMetric"))
            zf.writestr("content_performances.json", _rows_to_json(content_performances, "ContentPerformance"))
            zf.writestr("idea_selection_logs.json", _rows_to_json(idea_selection_logs, "IdeaSelectionLog"))
            zf.writestr("content_dna_profiles.json", _rows_to_json(content_dna_profiles, "ContentDNAProfile"))

        buf.seek(0)
        return buf.read()
