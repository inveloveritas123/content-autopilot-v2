"""
Feedback-API — Endpoints für das selbstlernende System.

Drei Feedback-Quellen:
1. Edit-Diff: Was ändert der Unternehmer am generierten Post?
2. Performance: LinkedIn-Metriken (manuell oder API)
3. Ideen-Selektion: Welche Ideen werden gewählt?
"""

import difflib
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant_id
from models.content_idea import ContentIdea
from models.content_performance import ContentPerformance, IdeaSelectionLog
from models.content_piece import ContentPiece

router = APIRouter(prefix="/feedback", tags=["feedback"])


# ═══ SCHEMAS ═══


class EditDiffRequest(BaseModel):
    content_piece_id: str
    final_text: str  # Der finale Text nach Bearbeitung durch den Unternehmer
    variant_index: int | None = 0


class PerformanceRequest(BaseModel):
    content_piece_id: str
    impressions: int | None = None
    reactions: int | None = None
    comments: int | None = None
    shares: int | None = None
    clicks: int | None = None
    linkedin_post_id: str | None = None
    posted_at: datetime | None = None


class IdeaSelectionRequest(BaseModel):
    selected_idea_ids: list[str]  # IDs der gewählten Ideen
    source_item_id: str  # Aus welchem Video/Artikel


class FeedbackStatsResponse(BaseModel):
    total_posts: int
    avg_edit_distance: float
    avg_engagement_rate: float
    top_angles: list[dict]
    improvement_trend: str


# ═══ ENDPOINTS ═══


@router.post("/edit-diff")
async def submit_edit_diff(
    req: EditDiffRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Speichere den Edit-Diff zwischen generiertem und finalem Post.

    Dies ist das stärkste Lernsignal: Es zeigt direkt, wo die KI daneben lag.
    """
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == req.content_piece_id,
            ContentPiece.tenant_id == tenant_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status_code=404, detail="Content piece not found")

    # Unified Diff berechnen
    original_lines = piece.content_text.splitlines(keepends=True)
    final_lines = req.final_text.splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(original_lines, final_lines, lineterm=""))

    # Levenshtein-ähnliche Distanz (einfache Char-Diff-Länge)
    edit_distance = sum(
        1 for a, b in zip(piece.content_text, req.final_text, strict=False) if a != b
    )
    edit_distance += abs(len(piece.content_text) - len(req.final_text))

    # Performance-Eintrag erstellen
    perf = ContentPerformance(
        content_piece_id=piece.id,
        tenant_id=tenant_id,
        was_selected=True,
        variant_index=req.variant_index,
        edit_diff=diff if diff else None,
        edit_distance=edit_distance,
        data_source="edit_diff",
    )
    db.add(perf)

    # Finalen Text im Content Piece aktualisieren
    piece.content_text = req.final_text
    piece.status = "approved"
    piece.approved_at = datetime.utcnow()
    piece.approved_by = "web_ui"
    piece.approval_method = "web_ui"

    await db.commit()

    return {
        "status": "saved",
        "edit_distance": edit_distance,
        "has_changes": bool(diff),
        "diff_preview": diff[:500] if diff else None,
    }


@router.post("/performance")
async def submit_performance(
    req: PerformanceRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Manuelle LinkedIn-Performance-Eingabe (nach 48h).

    MVP: Unternehmer gibt Impressions + Reactions ein.
    Später: LinkedIn API automatisch.
    """
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == req.content_piece_id,
            ContentPiece.tenant_id == tenant_id,
        )
    )
    piece = result.scalar_one_or_none()
    if not piece:
        raise HTTPException(status_code=404, detail="Content piece not found")

    # Engagement-Rate berechnen
    engagement_rate = None
    if req.impressions and req.impressions > 0:
        total_engagement = (
            (req.reactions or 0) + (req.comments or 0) + (req.shares or 0) + (req.clicks or 0)
        )
        engagement_rate = total_engagement / req.impressions

    # Posted-at Kontext
    posted_at = req.posted_at or datetime.utcnow()

    perf = ContentPerformance(
        content_piece_id=piece.id,
        tenant_id=tenant_id,
        linkedin_post_id=req.linkedin_post_id,
        impressions=req.impressions,
        reactions=req.reactions,
        comments=req.comments,
        shares=req.shares,
        clicks=req.clicks,
        engagement_rate=engagement_rate,
        was_published=True,
        posted_at=posted_at,
        day_of_week=posted_at.weekday(),
        hour_of_day=posted_at.hour,
        measured_at=datetime.utcnow(),
        data_source="manual",
    )
    db.add(perf)
    await db.commit()

    return {
        "status": "saved",
        "engagement_rate": round(engagement_rate * 100, 2) if engagement_rate else None,
        "verdict": _rate_engagement(engagement_rate),
    }


@router.post("/idea-selection")
async def submit_idea_selection(
    req: IdeaSelectionRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Tracke welche Ideen der Unternehmer auswählt.

    Wird aufgerufen wenn der Unternehmer eine oder mehrere Ideen zum Beantworten auswählt.
    """
    # Alle Ideen für dieses Source-Item laden
    result = await db.execute(
        select(ContentIdea).where(
            ContentIdea.source_item_id == req.source_item_id,
            ContentIdea.tenant_id == tenant_id,
        )
    )
    all_ideas = result.scalars().all()
    total_shown = len(all_ideas)

    selected_set = set(req.selected_idea_ids)
    logs = []

    for _idx, idea in enumerate(all_ideas):
        is_selected = str(idea.id) in selected_set
        log = IdeaSelectionLog(
            tenant_id=tenant_id,
            content_idea_id=idea.id,
            source_item_id=idea.source_item_id,
            total_ideas_shown=total_shown,
            was_selected=is_selected,
            selection_order=req.selected_idea_ids.index(str(idea.id)) + 1 if is_selected else None,
            angle=idea.angle,
            relevance_score=idea.relevance_score,
        )
        db.add(log)
        logs.append(log)

        # Status der gewählten Ideen aktualisieren
        if is_selected and idea.status == "new":
            idea.status = "questions_sent"

    await db.commit()

    return {
        "status": "tracked",
        "total_ideas": total_shown,
        "selected": len(selected_set),
        "ignored": total_shown - len(selected_set),
    }


@router.get("/stats")
async def get_feedback_stats(
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
):
    """Feedback-Statistiken für den Mandanten — für Dynamic Few-Shot und Dashboards."""
    result = await db.execute(
        select(ContentPerformance).where(
            ContentPerformance.tenant_id == tenant_id,
        )
    )
    performances = result.scalars().all()

    if not performances:
        return {
            "total_posts": 0,
            "avg_edit_distance": 0,
            "avg_engagement_rate": 0,
            "top_angles": [],
            "improvement_trend": "no_data",
        }

    edit_distances = [p.edit_distance for p in performances if p.edit_distance is not None]
    engagement_rates = [p.engagement_rate for p in performances if p.engagement_rate is not None]

    # Top-Angles nach Engagement
    angle_stats = {}
    for p in performances:
        if p.angle and p.engagement_rate:
            if p.angle not in angle_stats:
                angle_stats[p.angle] = []
            angle_stats[p.angle].append(p.engagement_rate)

    top_angles = sorted(
        [
            {"angle": k, "avg_engagement": sum(v) / len(v), "count": len(v)}
            for k, v in angle_stats.items()
        ],
        key=lambda x: x["avg_engagement"],
        reverse=True,
    )

    # Trend: Werden die Edit-Diffs kürzer? (= System wird besser)
    trend = "no_data"
    if len(edit_distances) >= 6:
        first_half = sum(edit_distances[: len(edit_distances) // 2]) / (len(edit_distances) // 2)
        second_half = sum(edit_distances[len(edit_distances) // 2 :]) / (
            len(edit_distances) - len(edit_distances) // 2
        )
        if second_half < first_half * 0.8:
            trend = "improving"
        elif second_half > first_half * 1.2:
            trend = "declining"
        else:
            trend = "stable"

    return {
        "total_posts": len(performances),
        "avg_edit_distance": round(sum(edit_distances) / len(edit_distances), 1)
        if edit_distances
        else 0,
        "avg_engagement_rate": round(sum(engagement_rates) / len(engagement_rates) * 100, 2)
        if engagement_rates
        else 0,
        "top_angles": top_angles[:5],
        "improvement_trend": trend,
    }


def _rate_engagement(rate: float | None) -> str:
    """Bewerte die Engagement-Rate nach LinkedIn-Standards."""
    if rate is None:
        return "unknown"
    if rate >= 0.05:
        return "excellent (>5%)"
    if rate >= 0.03:
        return "good (3-5%)"
    if rate >= 0.015:
        return "average (1.5-3%)"
    return "below_average (<1.5%)"
