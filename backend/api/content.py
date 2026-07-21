import contextlib
import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.content_piece import ContentPiece
from models.source import Source
from models.source_item import SourceItem
from models.tenant import Tenant

router = APIRouter()


class ContentUpdate(BaseModel):
    content_text: str | None = None
    content_metadata: dict | None = None
    status: str | None = None


class BulkApproveRequest(BaseModel):
    ids: list[str] | None = None  # None = approve all drafts


class BulkRejectRequest(BaseModel):
    ids: list[str] | None = None  # None = reject all drafts


class ScheduleData(BaseModel):
    scheduled_for: datetime


@router.get("/content")
async def list_content(
    channel: str | None = None,
    status: str | None = None,
    source_id: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    query = select(ContentPiece).where(ContentPiece.tenant_id == tenant.id)
    if channel:
        query = query.where(ContentPiece.channel == channel)
    if status:
        query = query.where(ContentPiece.status == status)
    if source_id:
        import uuid as _uuid

        query = query.join(SourceItem, ContentPiece.source_item_id == SourceItem.id).where(
            SourceItem.source_id == _uuid.UUID(source_id)
        )

    query = query.order_by(ContentPiece.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    pieces = result.scalars().all()

    # Enrich with source item info + source name in one batch query
    item_ids = [p.source_item_id for p in pieces if p.source_item_id]
    item_titles: dict = {}
    if item_ids:
        from sqlalchemy import select as sa_select

        from models.source import Source as _Source
        from models.source_item import SourceItem as _SI

        rows = (
            await db.execute(
                sa_select(_SI.id, _SI.title, _SI.url, _SI.source_id, _Source.name)
                .join(_Source, _SI.source_id == _Source.id, isouter=True)
                .where(_SI.id.in_(item_ids))
            )
        ).all()
        item_titles = {
            r.id: {
                "title": r.title,
                "url": r.url,
                "source_id": str(r.source_id) if r.source_id else None,
                "source_name": r.name,
            }
            for r in rows
        }

    return [
        {
            "id": str(p.id),
            "source_item_id": str(p.source_item_id) if p.source_item_id else None,
            "source_item_title": item_titles.get(p.source_item_id, {}).get("title")
            if p.source_item_id
            else None,
            "source_item_url": item_titles.get(p.source_item_id, {}).get("url")
            if p.source_item_id
            else None,
            "source_id": item_titles.get(p.source_item_id, {}).get("source_id")
            if p.source_item_id
            else None,
            "source_name": item_titles.get(p.source_item_id, {}).get("source_name")
            if p.source_item_id
            else None,
            "channel": p.channel,
            "content_text": p.content_text,
            "content_metadata": p.content_metadata,
            "status": p.status,
            "scheduled_for": p.scheduled_for.isoformat() if p.scheduled_for else None,
            "approved_by": p.approved_by,
            "approved_at": p.approved_at.isoformat() if p.approved_at else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in pieces
    ]


@router.get("/content/export")
async def export_content(
    status: str | None = Query(None, description="Filter by status (draft/approved/published)"),
    channel: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Export all content pieces as CSV for reporting."""
    query = select(ContentPiece).where(ContentPiece.tenant_id == tenant.id)
    if status:
        query = query.where(ContentPiece.status == status)
    if channel:
        query = query.where(ContentPiece.channel == channel)
    query = query.order_by(ContentPiece.created_at.desc())

    pieces = (await db.execute(query)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(
        [
            "id",
            "status",
            "channel",
            "angle",
            "variant",
            "content_text",
            "char_count",
            "created_at",
            "approved_at",
        ]
    )

    for p in pieces:
        meta = p.content_metadata or {}
        writer.writerow(
            [
                str(p.id),
                p.status or "",
                p.channel or "linkedin",
                meta.get("angle", ""),
                meta.get("variant", ""),
                (p.content_text or "").replace("\n", " ↵ "),
                len(p.content_text or ""),
                p.created_at.isoformat() if p.created_at else "",
                p.approved_at.isoformat() if getattr(p, "approved_at", None) else "",
            ]
        )

    output.seek(0)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M")
    filename = f"content_export_{ts}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/content/today-brief")
async def get_today_brief_route(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Forwards to the today-brief implementation (defined below)."""
    return await get_today_brief(tenant=tenant, db=db)


@router.get("/content/{content_id}")
async def get_content(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    return {
        "id": str(piece.id),
        "source_item_id": str(piece.source_item_id) if piece.source_item_id else None,
        "channel": piece.channel,
        "content_text": piece.content_text,
        "content_metadata": piece.content_metadata,
        "status": piece.status,
        "scheduled_for": piece.scheduled_for.isoformat() if piece.scheduled_for else None,
        "approved_by": piece.approved_by,
        "approved_at": piece.approved_at.isoformat() if piece.approved_at else None,
        "created_at": piece.created_at.isoformat() if piece.created_at else None,
    }


@router.put("/content/{content_id}")
async def update_content(
    content_id: str,
    data: ContentUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    update_data = data.model_dump(exclude_unset=True)

    # Enforce final approval constraint (#85): PUT cannot bypass publish guard
    if update_data.get("status") == "published":
        if piece.status != "approved" or not piece.approved_by:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "unapproved_post",
                    "message": "Post muss zuerst freigegeben werden — status 'published' via PUT nicht erlaubt ohne Approval",
                },
            )

    for field, value in update_data.items():
        setattr(piece, field, value)

    await db.commit()
    return {"id": str(piece.id), "status": piece.status}


@router.patch("/content/{content_id}/tags")
async def update_content_tags(
    content_id: str,
    data: dict,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Set the tags list for a content piece (stored in content_metadata.tags)."""
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    tags = data.get("tags", [])
    if not isinstance(tags, list):
        raise HTTPException(status_code=400, detail="tags must be a list")
    tags = [str(t).strip()[:40] for t in tags if str(t).strip()][:20]  # max 20 tags, 40 chars each

    meta = dict(piece.content_metadata or {})
    if tags:
        meta["tags"] = tags
    else:
        meta.pop("tags", None)
    piece.content_metadata = meta
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(piece, "content_metadata")
    await db.commit()
    return {"id": str(piece.id), "tags": tags}


@router.patch("/content/{content_id}/pillar")
async def update_content_pillar(
    content_id: str,
    data: dict,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Set or clear the content pillar (merges into content_metadata)."""
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")
    pillar = data.get("pillar")
    meta = dict(piece.content_metadata or {})
    if pillar:
        meta["pillar"] = pillar
    else:
        meta.pop("pillar", None)
    piece.content_metadata = meta
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(piece, "content_metadata")
    await db.commit()
    return {"id": str(piece.id), "pillar": pillar}


@router.post("/content/bulk-approve")
async def bulk_approve_content(
    data: BulkApproveRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Approve multiple content pieces at once. If ids is None, approves all drafts."""
    now = datetime.utcnow()
    if data.ids is not None:
        uuids = [uuid.UUID(i) for i in data.ids]
        query = select(ContentPiece).where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.id.in_(uuids),
        )
    else:
        query = select(ContentPiece).where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.status == "draft",
        )
    result = await db.execute(query)
    pieces = result.scalars().all()
    for p in pieces:
        p.status = "approved"
        p.approved_at = now
        p.approved_by = "web_ui"
        p.approval_method = "web_ui"
        p.human_reviewed = True  # W6: menschliche Prüfung dokumentiert (EU-AI-Act Art. 50)
    await db.commit()
    return {"approved": len(pieces), "ids": [str(p.id) for p in pieces]}


@router.post("/content/bulk-reject")
async def bulk_reject_content(
    data: BulkRejectRequest,
    source_id: str | None = Query(None),
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Reject multiple content pieces at once.
    Requires ids list OR source_id to prevent accidental mass-reject."""
    from fastapi import HTTPException as _HTTPException

    if data.ids is None and not source_id:
        raise _HTTPException(
            status_code=400,
            detail="Entweder ids[] oder source_id erforderlich, um versehentliches Massen-Ablehnen zu verhindern.",
        )
    if data.ids is not None:
        uuids = [uuid.UUID(i) for i in data.ids]
        query = select(ContentPiece).where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.id.in_(uuids),
        )
    elif source_id:
        _src_uuid = uuid.UUID(source_id)
        query = (
            select(ContentPiece)
            .join(SourceItem, ContentPiece.source_item_id == SourceItem.id)
            .where(
                ContentPiece.tenant_id == tenant.id,
                ContentPiece.status == "draft",
                SourceItem.source_id == _src_uuid,
            )
        )
    else:
        query = select(ContentPiece).where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.status == "draft",
        )
    pieces = (await db.execute(query)).scalars().all()
    for p in pieces:
        p.status = "rejected"
    await db.commit()
    return {"rejected": len(pieces), "ids": [str(p.id) for p in pieces]}


@router.post("/content/bulk-publish")
async def bulk_publish_content(
    data: BulkApproveRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Mark multiple content pieces as published at once."""
    if not data.ids:
        raise HTTPException(status_code=400, detail="ids[] erforderlich")
    uuids = [uuid.UUID(i) for i in data.ids]
    pieces = (
        (
            await db.execute(
                select(ContentPiece).where(
                    ContentPiece.tenant_id == tenant.id,
                    ContentPiece.id.in_(uuids),
                )
            )
        )
        .scalars()
        .all()
    )

    unapproved = [p for p in pieces if p.status != "approved" or not p.approved_by]
    if unapproved:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "unapproved_posts",
                "message": f"{len(unapproved)} Post(s) noch nicht freigegeben",
                "ids": [str(p.id) for p in unapproved],
            },
        )

    now = datetime.utcnow()
    for p in pieces:
        p.status = "published"
        p.approved_at = p.approved_at or now

    await db.commit()
    return {"published": len(pieces), "ids": [str(p.id) for p in pieces]}


@router.post("/content/{content_id}/mark-published")
async def mark_published(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Mark a content piece as published and update any linked scheduled post."""
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    # Enforce final approval constraint (#85)
    if piece.status != "approved" or not piece.approved_by:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "unapproved_post",
                "message": "Post muss zuerst manuell freigegeben werden (status='approved' und approved_by gesetzt)",
            },
        )

    piece.status = "published"
    piece.approved_at = piece.approved_at or datetime.utcnow()

    # Also update the linked ScheduledPost to published
    from models.scheduled_post import ScheduledPost

    sp_q = await db.execute(
        select(ScheduledPost).where(
            ScheduledPost.content_piece_id == piece.id,
            ScheduledPost.tenant_id == tenant.id,
        )
    )
    for sp in sp_q.scalars().all():
        sp.status = "published"
        sp.published_at = datetime.utcnow()

    await db.commit()
    return {
        "id": str(piece.id),
        "status": "published",
        "published_at": datetime.utcnow().isoformat(),
    }


@router.post("/content/{content_id}/approve")
async def approve_content(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    piece.status = "approved"
    piece.approved_at = datetime.utcnow()
    piece.approved_by = "web_ui"
    piece.approval_method = "web_ui"
    await db.commit()

    return {"id": str(piece.id), "status": "approved"}


@router.post("/content/{content_id}/schedule")
async def schedule_content(
    content_id: str,
    data: ScheduleData,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    piece = await db.get(ContentPiece, uuid.UUID(content_id))
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    piece.status = "scheduled"
    piece.scheduled_for = data.scheduled_for
    await db.commit()

    return {
        "id": str(piece.id),
        "status": "scheduled",
        "scheduled_for": data.scheduled_for.isoformat(),
    }


@router.post("/content/{content_id}/hashtags")
async def suggest_hashtags(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Suggest relevant hashtags for a content piece using LLM."""
    try:
        piece_uuid = uuid.UUID(content_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Content not found")
    piece = await db.get(ContentPiece, piece_uuid)
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    from services.llm import llm_service

    text = (piece.content_text or "")[:1000]
    prompt = (
        f"Analysiere diesen LinkedIn-Post und schlage 5-8 relevante deutsche und englische Hashtags vor.\n\n"
        f"Post:\n{text}\n\n"
        f'Antworte NUR mit einer JSON-Liste von Hashtags, z.B.: ["#KI", "#Handwerk", "#LinkedIn"]'
    )
    try:
        result = await llm_service.complete_json(prompt, purpose="tagging")
        if isinstance(result, list):
            return {"hashtags": result[:10]}
        return {"hashtags": []}
    except Exception as e:
        return {"hashtags": [], "error": str(e)}


@router.get("/hook-library")
async def get_hook_library(
    angle: str | None = None,
    tenant: Tenant = Depends(get_tenant),
):
    """Hook-Bibliothek: Bewährte Einstiegssätze für LinkedIn-Posts nach Post-Typ."""
    hooks = {
        "meinung": [
            "Ich sage mal was Unpopuläres:",
            "Meine ehrliche Meinung zu {thema} — viele werden das nicht hören wollen:",
            "Warum ich {mainstream_meinung} für falsch halte:",
            "Hot take: {these}",
            "Unpopular opinion: {these}",
        ],
        "howto": [
            "In {zeitraum} habe ich {ergebnis} erreicht. So geht's:",
            "3 Dinge, die mir bei {thema} wirklich geholfen haben:",
            "Das einzige {system/framework} das du für {ziel} brauchst:",
            "Niemand redet darüber, aber {geheimtipp} ist das Wichtigste bei {thema}:",
            "Schritt für Schritt: So {ziel} in {zeitraum}:",
        ],
        "story": [
            "Vor {zeitraum} hatte ich ein Problem. Heute nicht mehr. Was passiert ist:",
            "{fehler} war der teuerste Fehler meiner Karriere. Was ich gelernt habe:",
            "Ein Kunde rief mich an und sagte: '{zitat}'. Was dann passierte:",
            "Ich war kurz davor aufzugeben. Dann passierte das:",
            "Vor {zeitraum} wusste ich noch nicht, dass {einsicht}. Heute ist das mein wichtigstes Prinzip:",
        ],
        "kontroverse": [
            "Niemand will das hören, aber {aussage}",
            "Das Internet liegt falsch bei {thema}:",
            "Ich widerspreche fast allen Experten wenn es um {thema} geht. Hier ist warum:",
            "{beliebte_aussage} — stimmt so nicht. Meine Gegenmeinung:",
            "Warte mal kurz: {frage die alle anders beantworten würden}",
        ],
        "statistik": [
            "{zahl}% der {gruppe} wissen nicht, dass {fakt}. Das kostet sie {konsequenz}:",
            "Eine Studie hat mich schockiert: {fakt}",
            "{zahl} — diese Zahl hat mein Denken über {thema} komplett verändert:",
            "Die meisten kennen diese Zahl nicht: {statistik}. Was das für dich bedeutet:",
        ],
        "trend": [
            "{trend} verändert gerade {branche} grundlegend. Bist du bereit?",
            "In 3 Jahren wird {vorhersage}. Was du jetzt tun solltest:",
            "Alle reden über {trend}, aber keiner redet über {konsequenz}:",
            "Der Trend den du noch nicht auf dem Schirm hast: {trend}",
        ],
    }

    if angle and angle in hooks:
        return {"angle": angle, "hooks": hooks[angle]}
    return {"hooks": hooks}


@router.post("/content/{content_id}/repurpose")
async def repurpose_content(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate 3 variants of a post with different angles using LLM."""
    try:
        piece_uuid = uuid.UUID(content_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=404, detail="Content not found")

    piece = await db.get(ContentPiece, piece_uuid)
    if not piece or piece.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Content not found")

    from services.llm import llm_service

    original = (piece.content_text or "")[:1500]
    original_angle = (piece.content_metadata or {}).get("angle", "allgemein")
    all_angles = ["meinung", "howto", "story", "kontroverse", "statistik", "trend"]
    target_angles = [a for a in all_angles if a != original_angle][:3]

    prompt = (
        f"Du bist ein LinkedIn-Ghostwriter. Du bekommst einen bestehenden LinkedIn-Post "
        f"und sollst 3 Varianten davon schreiben — jeweils mit einem anderen Post-Stil.\n\n"
        f"ORIGINAL POST:\n{original}\n\n"
        f"Erstelle 3 neue Varianten mit diesen Stilen: {', '.join(target_angles)}\n\n"
        f"Antworte NUR mit einem JSON-Array. Jedes Objekt:\n"
        f"- \"angle\": Stil (genau einer von: {', '.join(target_angles)})\n"
        f"- \"text\": neuer LinkedIn-Post (Deutsch, gleiche Kernaussage, anderer Stil, 800-1200 Zeichen)\n\n"
        f"Wichtig: Gleiche Fakten und Kernaussage, aber andere Perspektive. Kein Lorem ipsum."
    )

    try:
        variants = await llm_service.complete_json(prompt, purpose="generation")
        if not isinstance(variants, list):
            raise HTTPException(status_code=500, detail="LLM returned invalid response")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e!s}")

    created = []
    for v in variants[:3]:
        text = (v.get("text") or "").strip()
        angle = v.get("angle", "variant")
        if not text:
            continue
        base_meta = dict(piece.content_metadata or {})
        base_meta.update(
            {
                "angle": angle,
                "variant": "repurposed",
                "repurposed_from": str(piece.id),
            }
        )
        new_piece = ContentPiece(
            source_item_id=piece.source_item_id,
            tenant_id=tenant.id,
            channel=piece.channel,
            content_text=text,
            status="draft",
            content_metadata=base_meta,
        )
        db.add(new_piece)
        created.append({"angle": angle, "char_count": len(text)})

    await db.commit()
    return {"repurposed": len(created), "variants": created}


# ── Multi-Format Repurposer ──────────────────────────────────────────────────


@router.post("/content/{content_id}/repurpose-formats")
async def repurpose_formats(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Convert a LinkedIn post into 3 other formats: Twitter thread, email newsletter intro, blog intro.
    Returns all 3 formats in-memory — nothing saved until user chooses to.
    """
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.tenant_id == tenant.id,
        )
    )
    piece = result.scalars().first()
    if not piece:
        raise HTTPException(status_code=404, detail="Content not found")
    if not piece.content_text:
        raise HTTPException(status_code=400, detail="Content has no text")

    from services.llm import llm_service

    original = (piece.content_text or "")[:2000]

    prompt = (
        "Du bist ein Content-Repurposing-Experte. Konvertiere den folgenden LinkedIn-Post in 3 andere Formate.\n\n"
        f"LINKEDIN-POST ORIGINAL:\n{original}\n\n"
        "Erstelle:\n\n"
        "1. TWITTER/X-THREAD (5-7 Tweets)\n"
        "- Jeder Tweet max. 280 Zeichen\n"
        "- Trenne Tweets mit '---'\n"
        "- Tweet 1 = Hook (stärkster Satz)\n"
        "- Letzter Tweet = CTA oder Zusammenfassung\n\n"
        "2. E-MAIL NEWSLETTER INTRO (150-200 Wörter)\n"
        "- Persönliche Anrede: 'Liebe Community,'\n"
        "- Fesselnder Einstieg der zur Weiterlektüre animiert\n"
        "- Endet mit: 'Heute sprechen wir über: [THEMA]'\n\n"
        "3. BLOG-POST OUTLINE\n"
        "- H1: Titel (SEO-optimiert, neugierig)\n"
        "- H2: 4-5 Abschnitte mit je 1-2 Satz Beschreibung\n"
        "- CTA am Ende\n\n"
        "Antworte NUR mit einem JSON-Objekt:\n"
        "{\n"
        '  "twitter_thread": "Tweet1\\n---\\nTweet2\\n---\\n...",\n'
        '  "email_newsletter": "Liebe Community, ...",\n'
        '  "blog_outline": "# Titel\\n\\n## Abschnitt 1\\n..."\n'
        "}\n"
        "Alle Texte auf Deutsch."
    )

    try:
        raw = await llm_service.complete_json(prompt, purpose="generation")
        if not isinstance(raw, dict):
            raise HTTPException(status_code=500, detail="LLM returned invalid response")

        twitter = (raw.get("twitter_thread") or "").strip()
        email = (raw.get("email_newsletter") or "").strip()
        blog = (raw.get("blog_outline") or "").strip()

        if not twitter and not email and not blog:
            raise HTTPException(status_code=500, detail="LLM returned empty formats")

        # Count tweets
        tweets = [t.strip() for t in twitter.split("---") if t.strip()] if twitter else []

        return {
            "content_id": content_id,
            "original_chars": len(piece.content_text),
            "twitter_thread": {
                "text": twitter,
                "tweets": tweets,
                "tweet_count": len(tweets),
            },
            "email_newsletter": {
                "text": email,
                "chars": len(email),
            },
            "blog_outline": {
                "text": blog,
                "chars": len(blog),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── A/B Variant Generator ────────────────────────────────────────────────────


@router.post("/content/{content_id}/variants")
async def generate_ab_variants(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate 2 in-memory A/B variants (List vs Story). No DB save until user picks one."""
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.tenant_id == tenant.id,
        )
    )
    piece = result.scalars().first()
    if not piece:
        raise HTTPException(status_code=404, detail="Content not found")
    if not piece.content_text:
        raise HTTPException(status_code=400, detail="Content has no text")

    from services.llm import llm_service

    original = (piece.content_text or "")[:1800]
    prompt = (
        "Du bist ein LinkedIn-Ghostwriter für DACH B2B-Zielgruppen.\n"
        "Schreibe ZWEI strukturell verschiedene Versionen des folgenden LinkedIn-Posts.\n\n"
        "VERSION A — Listen-Format:\n"
        "- Beginnt mit einem starken Hook (1 Zeile)\n"
        "- Strukturiert mit nummerierten Punkten oder Bullet-Points\n"
        "- Klar, scannbar, lehrreich — 700–1000 Zeichen\n\n"
        "VERSION B — Story-Format:\n"
        "- Beginnt mit einer persönlichen Situation oder überraschenden Aussage\n"
        "- Fließender narrativer Text, keine Listen, Ich-Perspektive\n"
        "- Emotional, authentisch — 700–1000 Zeichen\n\n"
        f"ORIGINAL:\n{original}\n\n"
        "Antworte NUR mit einem JSON-Objekt:\n"
        '{ "variant_a": "<Listen-Format Text>", "variant_b": "<Story-Format Text>" }\n'
        "Gleiche Kernaussage, anderer Stil. Beide auf Deutsch. Kein Lorem ipsum."
    )

    try:
        raw = await llm_service.complete_json(prompt, purpose="generation")
        if not isinstance(raw, dict):
            raise HTTPException(status_code=500, detail="LLM returned invalid response")
        va = (raw.get("variant_a") or "").strip()
        vb = (raw.get("variant_b") or "").strip()
        if not va or not vb:
            raise HTTPException(status_code=500, detail="LLM returned empty variants")
        return {
            "content_id": content_id,
            "original_chars": len(piece.content_text),
            "variant_a": {"style": "list", "label": "Listen-Format", "text": va, "chars": len(va)},
            "variant_b": {"style": "story", "label": "Story-Format", "text": vb, "chars": len(vb)},
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class QuickCreateRequest(BaseModel):
    topic: str
    angle: str | None = "thought_leadership"
    pillar: str | None = None
    style_notes: str | None = None
    channel: str = "linkedin"


class SaveDirectRequest(BaseModel):
    """Speichert einen von Claude direkt geschriebenen Post — ohne Backend-LLM."""

    content_text: str
    title: str | None = None
    angle: str | None = "manual"
    pillar: str | None = None
    channel: str = "linkedin"
    idea_id: str | None = None  # optional: Link zur Quell-Idee


@router.post("/content/save-direct")
async def save_direct_post(
    data: SaveDirectRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Speichert einen fertig geschriebenen Post (z.B. von Claude direkt) ohne LLM-Kosten."""
    # Find or create the "manual" source
    from models.source import Source

    manual_source_q = await db.execute(
        select(Source).where(Source.tenant_id == tenant.id, Source.type == "manual")
    )
    manual_source = manual_source_q.scalars().first()
    if not manual_source:
        manual_source = Source(
            tenant_id=tenant.id,
            name="Manuell erstellt",
            type="manual",
            language="de",
            is_active=True,
        )
        db.add(manual_source)
        await db.flush()

    # Create source item stub
    source_item = SourceItem(
        source_id=manual_source.id,
        tenant_id=tenant.id,
        external_id=str(uuid.uuid4()),
        title=(data.title or data.content_text[:80]).strip(),
        content_type="manual",
        status="processed",
    )
    db.add(source_item)
    await db.flush()

    meta: dict = {"angle": data.angle or "manual", "claude_direct": True}
    if data.pillar:
        meta["pillar"] = data.pillar
    if data.idea_id:
        meta["idea_id"] = data.idea_id

    piece = ContentPiece(
        source_item_id=source_item.id,
        tenant_id=tenant.id,
        channel=data.channel,
        content_text=data.content_text.strip(),
        status="draft",
        content_metadata=meta,
    )
    db.add(piece)

    # Mark idea as post_generated if linked
    if data.idea_id:
        try:
            from models.content_idea import ContentIdea

            idea = await db.get(ContentIdea, uuid.UUID(data.idea_id))
            if idea and idea.tenant_id == tenant.id:
                idea.status = "post_generated"
        except Exception:
            pass

    await db.commit()
    await db.refresh(piece)

    return {
        "id": str(piece.id),
        "content_text": piece.content_text,
        "status": piece.status,
        "char_count": len(piece.content_text),
        "angle": data.angle,
        "message": "Post gespeichert — bereit zur Freigabe",
    }


@router.post("/content/quick-create")
async def quick_create_post(
    data: QuickCreateRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate a LinkedIn post from a topic using AI — no source/scraping needed."""
    from services.llm import llm_service

    # Find or create the "manual" source for this tenant
    manual_source_q = await db.execute(
        select(Source).where(Source.tenant_id == tenant.id, Source.type == "manual")
    )
    manual_source = manual_source_q.scalars().first()
    if not manual_source:
        manual_source = Source(
            tenant_id=tenant.id,
            name="Manuell erstellt",
            type="manual",
            language="de",
            is_active=True,
        )
        db.add(manual_source)
        await db.flush()

    # Create a source item for this topic
    item_id = str(uuid.uuid4())
    source_item = SourceItem(
        source_id=manual_source.id,
        tenant_id=tenant.id,
        external_id=item_id,
        title=data.topic[:500],
        content_type="manual",
        status="processed",
    )
    db.add(source_item)
    await db.flush()

    # Build LLM prompt
    style_hint = f"\nStil-Hinweis: {data.style_notes}" if data.style_notes else ""
    angle_map = {
        "thought_leadership": "Thought-Leadership (persönliche Meinung, Expertise zeigen)",
        "how_to": "How-To (praktische Tipps, Schritt-für-Schritt)",
        "personal_story": "Persönliche Story (Erfahrung, Emotion, Authentizität)",
        "industry_news": "Branchennews-Einordnung (Kontext, Analyse, Meinung)",
        "product_service": "Produkt/Service (Nutzen zeigen, nicht verkäuferisch)",
    }
    angle_label = angle_map.get(data.angle, data.angle or "Thought Leadership")

    prompt = (
        f"Du bist ein LinkedIn-Ghostwriter für deutschsprachige B2B-Fachleute (DACH-Raum).\n\n"
        f"Schreibe einen hochwertigen LinkedIn-Post über folgendes Thema:\n"
        f"THEMA: {data.topic}\n"
        f"STIL: {angle_label}{style_hint}\n\n"
        f"Regeln:\n"
        f"- Auf Deutsch, professionell aber persönlich\n"
        f"- 800-1.400 Zeichen (ideal für LinkedIn-Algorithmus)\n"
        f"- Starker Hook (erste 210 Zeichen sind entscheidend!)\n"
        f"- 3-5 kurze Absätze mit Leerzeilen\n"
        f"- Endet mit einer konkreten Frage ans Netzwerk\n"
        f"- Kein Hashtag-Spam (max. 3 am Ende)\n"
        f'- Kein "Liebe Community" oder generische Floskeln\n\n'
        f"Antworte NUR mit dem Post-Text, ohne Einleitung oder Erklärung."
    )

    try:
        result = await llm_service.complete(prompt, purpose="generation")
        post_text = (result or "").strip()
        if not post_text:
            raise HTTPException(status_code=500, detail="LLM returned empty response")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e!s}")

    meta = {"angle": data.angle or "manual", "quick_created": True}
    if data.pillar:
        meta["pillar"] = data.pillar

    piece = ContentPiece(
        source_item_id=source_item.id,
        tenant_id=tenant.id,
        channel=data.channel,
        content_text=post_text,
        status="draft",
        content_metadata=meta,
    )
    db.add(piece)
    await db.commit()
    await db.refresh(piece)

    return {
        "id": str(piece.id),
        "content_text": piece.content_text,
        "status": piece.status,
        "char_count": len(piece.content_text),
        "angle": data.angle,
        "pillar": data.pillar,
    }


class SeriesCreateRequest(BaseModel):
    topic: str
    pillar: str | None = None
    channel: str = "linkedin"


@router.post("/content/create-series")
async def create_content_series(
    data: SeriesCreateRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate a 3-post LinkedIn series: Hook/Intro → Deep Dive → CTA/Conclusion."""
    from services.llm import llm_service

    # Find or create manual source
    manual_source_q = await db.execute(
        select(Source).where(Source.tenant_id == tenant.id, Source.type == "manual")
    )
    manual_source = manual_source_q.scalars().first()
    if not manual_source:
        manual_source = Source(
            tenant_id=tenant.id,
            name="Manuell erstellt",
            type="manual",
            language="de",
            is_active=True,
        )
        db.add(manual_source)
        await db.flush()

    # Create shared source item for the series
    source_item = SourceItem(
        source_id=manual_source.id,
        tenant_id=tenant.id,
        external_id=str(uuid.uuid4()),
        title=f"Serie: {data.topic[:480]}",
        content_type="manual",
        status="processed",
    )
    db.add(source_item)
    await db.flush()

    series_posts = [
        {
            "part": 1,
            "label": "Intro / Hook",
            "angle": "hook",
            "instructions": (
                "Post 1 von 3 einer Serie. Ziel: Neugier wecken, Thema einführen, Follower auf die nächsten Posts vorbereiten. "
                "Enden mit: 'In den nächsten Tagen teile ich [was kommt]...' oder 'Morgen: [Thema Part 2]'"
            ),
        },
        {
            "part": 2,
            "label": "Deep Dive",
            "angle": "expertise",
            "instructions": (
                "Post 2 von 3 einer Serie. Ziel: Hauptinhalt liefern, konkrete Tipps/Erkenntnisse, maximaler Mehrwert. "
                "Beginnt mit: '[Gestern sprach ich über X]...' oder 'Teil 2 meiner Serie über [Thema]:'. "
                "Endet mit Verweis auf den Abschluss-Post."
            ),
        },
        {
            "part": 3,
            "label": "Fazit / CTA",
            "angle": "cta",
            "instructions": (
                "Post 3 von 3 einer Serie. Ziel: Zusammenfassung, Handlungsaufforderung, Community einbeziehen. "
                "Beginnt mit: 'Abschluss meiner Serie über [Thema]:'. "
                "Enthält konkrete nächste Schritte für die Leser. Endet mit starker Frage."
            ),
        },
    ]

    prompt = (
        f"Du bist ein LinkedIn-Ghostwriter. Erstelle eine 3-teilige LinkedIn-Post-Serie über:\n"
        f"THEMA: {data.topic}\n\n"
        f"Regeln für alle 3 Posts:\n"
        f"- Auf Deutsch, B2B DACH-Raum\n"
        f"- 700-1.200 Zeichen pro Post\n"
        f"- Die Posts bauen logisch aufeinander auf\n"
        f"- Jeder Post funktioniert auch einzeln\n"
        f"- Kein Jargon, persönlich und direkt\n\n"
        f"Post 1 (Intro/Hook): Neugier wecken, Thema einführen, auf Part 2 verweisen\n"
        f"Post 2 (Deep Dive): Hauptinhalt mit konkreten Tipps/Erkenntnissen\n"
        f"Post 3 (Fazit/CTA): Zusammenfassung + starke Handlungsaufforderung\n\n"
        f"Antworte NUR mit einem JSON-Array mit 3 Objekten:\n"
        f'[{{"part": 1, "label": "Intro", "text": "..."}}, ...]\n'
        f"Kein weiterer Text außerhalb des JSON-Arrays."
    )

    try:
        result = await llm_service.complete_json(prompt, purpose="generation")
        if not isinstance(result, list) or len(result) < 3:
            raise HTTPException(status_code=500, detail="LLM returned invalid series structure")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e!s}")

    series_id = str(uuid.uuid4())
    created = []
    for _i, (meta_info, llm_part) in enumerate(zip(series_posts, result[:3], strict=False)):
        text = (llm_part.get("text") or "").strip()
        if not text:
            continue
        meta = {
            "angle": meta_info["angle"],
            "series_id": series_id,
            "series_part": meta_info["part"],
            "series_label": meta_info["label"],
            "series_topic": data.topic,
            "quick_created": True,
        }
        if data.pillar:
            meta["pillar"] = data.pillar

        piece = ContentPiece(
            source_item_id=source_item.id,
            tenant_id=tenant.id,
            channel=data.channel,
            content_text=text,
            status="draft",
            content_metadata=meta,
        )
        db.add(piece)
        created.append(
            {
                "part": meta_info["part"],
                "label": meta_info["label"],
                "char_count": len(text),
                "preview": text[:120],
            }
        )

    await db.commit()
    return {
        "series_id": series_id,
        "topic": data.topic,
        "posts_created": len(created),
        "parts": created,
    }


class UrlPostRequest(BaseModel):
    url: str
    angle: str | None = "thought_leadership"
    pillar: str | None = None
    style_notes: str | None = None
    channel: str = "linkedin"


@router.post("/content/post-from-url")
async def post_from_url(
    data: UrlPostRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate a LinkedIn post from any URL (article, YouTube, blog post)."""
    import re
    from html.parser import HTMLParser

    import httpx

    from services.llm import llm_service

    class MetaExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.title = ""
            self.description = ""
            self.og_title = ""
            self.og_description = ""
            self._in_title = False

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            if tag == "title":
                self._in_title = True
            elif tag == "meta":
                name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
                content = attrs_dict.get("content") or ""
                if name in ("description", "twitter:description"):
                    self.description = content[:600]
                elif name == "og:title":
                    self.og_title = content[:300]
                elif name == "og:description":
                    self.og_description = content[:600]

        def handle_endtag(self, tag):
            if tag == "title":
                self._in_title = False

        def handle_data(self, data):
            if self._in_title and not self.title:
                self.title = data.strip()[:300]

    # Fetch URL with timeout
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; ContentBot/1.0)"}
            resp = await client.get(data.url, headers=headers)
            html = resp.text[:50000]  # Limit to first 50KB
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"URL konnte nicht geladen werden: {e!s}")

    # Extract meta info
    extractor = MetaExtractor()
    with contextlib.suppress(Exception):
        extractor.feed(html)

    page_title = extractor.og_title or extractor.title or data.url
    page_desc = extractor.og_description or extractor.description or ""

    # Also try to extract some body text (first 1000 chars of visible text)
    clean_html = re.sub(
        r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    body_text = re.sub(r"<[^>]+>", " ", clean_html)
    body_text = re.sub(r"\s+", " ", body_text).strip()[:1500]

    if not page_title and not page_desc and not body_text:
        raise HTTPException(
            status_code=422, detail="Keine verwertbaren Inhalte von der URL extrahiert"
        )

    angle_map = {
        "thought_leadership": "Thought-Leadership (persönliche Meinung, Expertise zeigen)",
        "how_to": "How-To (praktische Tipps)",
        "personal_story": "Persönliche Story (Erfahrung, Emotion)",
        "industry_news": "Branchennews-Einordnung (Kontext, Analyse)",
        "product_service": "Produkt/Service-Nutzen",
    }
    angle_label = angle_map.get(data.angle, data.angle or "Thought Leadership")
    style_hint = f"\nStil-Hinweis: {data.style_notes}" if data.style_notes else ""

    prompt = (
        f"Du bist ein LinkedIn-Ghostwriter für deutschsprachige B2B-Fachleute.\n\n"
        f"Schreibe einen LinkedIn-Post basierend auf diesem Artikel/Video:\n\n"
        f"TITEL: {page_title}\n"
        f"BESCHREIBUNG: {page_desc}\n"
        f"URL: {data.url}\n"
        + (f"INHALT (Auszug): {body_text[:800]}\n" if body_text else "")
        + f"\nPOST-STIL: {angle_label}{style_hint}\n\n"
        f"Regeln:\n"
        f"- Auf Deutsch, B2B DACH-Raum\n"
        f"- 800-1.400 Zeichen\n"
        f"- Eigene Meinung/Einordnung zum Inhalt — NICHT einfach zusammenfassen\n"
        f"- Starker Hook (erste 210 Zeichen entscheidend)\n"
        f"- 3-5 kurze Absätze\n"
        f"- Endet mit Frage ans Netzwerk\n"
        f"- Quelle nicht direkt erwähnen (kein 'Laut diesem Artikel...')\n\n"
        f"Antworte NUR mit dem Post-Text."
    )

    try:
        post_text = (await llm_service.complete(prompt, purpose="generation") or "").strip()
        if not post_text:
            raise HTTPException(status_code=500, detail="LLM returned empty response")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e!s}")

    # Find/create manual source
    manual_source_q = await db.execute(
        select(Source).where(Source.tenant_id == tenant.id, Source.type == "manual")
    )
    manual_source = manual_source_q.scalars().first()
    if not manual_source:
        manual_source = Source(
            tenant_id=tenant.id,
            name="Manuell erstellt",
            type="manual",
            language="de",
            is_active=True,
        )
        db.add(manual_source)
        await db.flush()

    source_item = SourceItem(
        source_id=manual_source.id,
        tenant_id=tenant.id,
        external_id=str(uuid.uuid4()),
        title=page_title[:500],
        url=data.url[:500],
        content_type="manual",
        status="processed",
    )
    db.add(source_item)
    await db.flush()

    meta = {
        "angle": data.angle or "manual",
        "source_url": data.url,
        "source_title": page_title,
        "quick_created": True,
    }
    if data.pillar:
        meta["pillar"] = data.pillar

    piece = ContentPiece(
        source_item_id=source_item.id,
        tenant_id=tenant.id,
        channel=data.channel,
        content_text=post_text,
        status="draft",
        content_metadata=meta,
    )
    db.add(piece)
    await db.commit()
    await db.refresh(piece)

    return {
        "id": str(piece.id),
        "content_text": piece.content_text,
        "status": piece.status,
        "char_count": len(piece.content_text),
        "source_title": page_title,
        "source_url": data.url,
    }


# ── AI Post Rewriter ────────────────────────────────────────────────────────


class RewriteRequest(BaseModel):
    mode: str  # shorter | hook | cta | professional | casual


REWRITE_PROMPTS = {
    "shorter": """Du bist LinkedIn-Content-Experte. Kürze den folgenden Post auf 600–900 Zeichen.
Behalte die Kernbotschaft, den Hook und die wichtigsten Punkte. Entferne Füllwörter und redundante Sätze.
Gib NUR den überarbeiteten Post zurück, ohne Kommentar oder Erklärung.

Original:
{text}""",
    "hook": """Du bist LinkedIn-Content-Experte spezialisiert auf DACH B2B.
Die ersten 2-3 Zeilen eines LinkedIn-Posts entscheiden ob jemand „mehr anzeigen" klickt.
Schreibe die ersten 2-3 Zeilen des folgenden Posts komplett neu: provokanter, neugieriger, emotionaler.
Der Rest des Posts bleibt unverändert. Gib den GESAMTEN Post zurück.

Original:
{text}""",
    "cta": """Du bist LinkedIn-Content-Experte. Der folgende Post braucht einen stärkeren Abschluss.
Schreibe die letzten 1-2 Zeilen neu als klarer Call-to-Action oder Engagement-Frage (z.B. „Was denkst du?" oder „Hast du ähnliche Erfahrungen?").
Der Rest des Posts bleibt unverändert. Gib den GESAMTEN Post zurück.

Original:
{text}""",
    "professional": """Du bist LinkedIn-Content-Experte für B2B DACH-Kommunikation.
Mache den folgenden Post professioneller und seriöser: weniger Umgangssprache, präzisere Formulierungen, mehr Autorität.
Behalte die Kernaussage. Gib NUR den überarbeiteten Post zurück.

Original:
{text}""",
    "casual": """Du bist LinkedIn-Content-Experte. Mache den folgenden Post zugänglicher und persönlicher:
lockerer Ton, kürzere Sätze, mehr Ich-Perspektive, weniger Fachvokabular.
Behalte die Kernaussage. Gib NUR den überarbeiteten Post zurück.

Original:
{text}""",
}


@router.post("/content/{content_id}/rewrite")
async def rewrite_content(
    content_id: str,
    data: RewriteRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Rewrite a content piece using LLM with a specific improvement mode."""
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.tenant_id == tenant.id,
        )
    )
    piece = result.scalars().first()
    if not piece:
        raise HTTPException(status_code=404, detail="Content not found")
    if not piece.content_text:
        raise HTTPException(status_code=400, detail="Content has no text to rewrite")

    mode = data.mode
    if mode not in REWRITE_PROMPTS:
        raise HTTPException(
            status_code=400, detail=f"Unknown mode: {mode}. Use: {list(REWRITE_PROMPTS.keys())}"
        )

    from services.llm import llm_service

    prompt = REWRITE_PROMPTS[mode].format(text=piece.content_text)
    try:
        rewritten = (await llm_service.complete(prompt, purpose="generation") or "").strip()
        if not rewritten:
            raise HTTPException(status_code=500, detail="LLM returned empty response")
        return {
            "id": str(piece.id),
            "mode": mode,
            "original_text": piece.content_text,
            "rewritten_text": rewritten,
            "original_chars": len(piece.content_text),
            "rewritten_chars": len(rewritten),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AI Daily Content Brief ───────────────────────────────────────────────────

_PILLAR_LABELS = {
    "thought_leadership": "Thought Leadership",
    "how_to": "How-To / Anleitung",
    "personal_story": "Persönliche Story",
    "industry_news": "Branchennews",
    "product_service": "Produkt / Service",
}

_BEST_SLOTS = {
    0: {"name": "Montag", "hours": [8, 12, 17]},
    1: {"name": "Dienstag", "hours": [8, 9, 12, 17]},
    2: {"name": "Mittwoch", "hours": [8, 9, 12, 17]},
    3: {"name": "Donnerstag", "hours": [8, 9, 12]},
    4: {"name": "Freitag", "hours": [8, 12]},
    5: {"name": "Samstag", "hours": []},
    6: {"name": "Sonntag", "hours": []},
}


@router.get("/content/today-brief")
async def get_today_brief(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """AI Daily Content Brief — pillar gaps + best posting time + recommended post."""
    now = datetime.now()
    weekday = now.weekday()
    today_name = _BEST_SLOTS[weekday]["name"]
    today_hours = _BEST_SLOTS[weekday]["hours"]
    is_good_day = weekday < 5 and len(today_hours) >= 2

    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.status.in_(["draft", "approved", "published", "scheduled"]),
        )
    )
    pieces = result.scalars().all()

    pillar_counts = {k: 0 for k in _PILLAR_LABELS}
    total_approved = 0
    drafts = 0

    for p in pieces:
        meta = p.content_metadata or {}
        pillar = meta.get("pillar")
        if pillar and pillar in pillar_counts:
            pillar_counts[pillar] += 1
        if p.status == "approved":
            total_approved += 1
        elif p.status == "draft":
            drafts += 1

    gap_pillar = min(pillar_counts, key=lambda k: pillar_counts[k])
    gap_label = _PILLAR_LABELS.get(gap_pillar, gap_pillar)
    gap_count = pillar_counts[gap_pillar]

    result2 = await db.execute(
        select(ContentPiece)
        .where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.status == "approved",
        )
        .order_by(ContentPiece.created_at.asc())
        .limit(10)
    )
    approved_posts = result2.scalars().all()

    recommended_post = None
    for p in approved_posts:
        if (p.content_metadata or {}).get("pillar") == gap_pillar:
            recommended_post = p
            break
    if not recommended_post and approved_posts:
        recommended_post = approved_posts[0]

    next_slot = None
    if is_good_day and today_hours:
        for hour in today_hours:
            slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if slot > now:
                next_slot = slot
                break

    prompts = {
        "thought_leadership": "Teile eine kontroverse These — beginne mit 'Unpopuläre Meinung:'",
        "how_to": "Erkläre in 5 Schritten, wie du ein konkretes Problem gelöst hast",
        "personal_story": "Erzähle von einem Fehler und was du dabei gelernt hast",
        "industry_news": "Kommentiere eine aktuelle Entwicklung — was bedeutet sie für deine Zielgruppe?",
        "product_service": "Zeige anhand eines echten Kunden-Ergebnisses, welchen Wert deine Arbeit schafft",
    }
    writing_prompt = prompts.get(gap_pillar, "Teile eine Erkenntnis aus dieser Woche")

    score = 0
    if total_approved > 0:
        score += 30
    if total_approved >= 5:
        score += 20
    if drafts > 0:
        score += 15
    if is_good_day:
        score += 15
    if next_slot:
        score += 10
    if gap_count == 0:
        score -= 10
    score = max(0, min(100, score))

    return {
        "today": {
            "weekday": weekday,
            "day_name": today_name,
            "is_good_posting_day": is_good_day,
            "best_hours": today_hours,
            "next_optimal_slot": next_slot.strftime("%H:%M") if next_slot else None,
            "next_optimal_dt": next_slot.isoformat() if next_slot else None,
        },
        "queue": {"approved": total_approved, "drafts": drafts},
        "pillar_gap": {
            "key": gap_pillar,
            "label": gap_label,
            "count": gap_count,
            "writing_prompt": writing_prompt,
        },
        "recommended_post": {
            "id": str(recommended_post.id),
            "preview": (recommended_post.content_text or "")[:200],
            "angle": (recommended_post.content_metadata or {}).get("angle", ""),
            "pillar": (recommended_post.content_metadata or {}).get("pillar", ""),
            "chars": len(recommended_post.content_text or ""),
        }
        if recommended_post
        else None,
        "momentum_score": score,
        "pillar_counts": pillar_counts,
    }


# ── Content Performance Predictor (Cycle 39) ────────────────────────────────


@router.post("/content/{content_id}/predict-performance")
async def predict_performance(
    content_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Predict engagement performance of a post based on historical patterns.
    Returns estimated reach/likes/comments, key strength/weakness signals,
    and 3 actionable improvement tips.
    """
    result = await db.execute(
        select(ContentPiece).where(
            ContentPiece.id == content_id,
            ContentPiece.tenant_id == tenant.id,
        )
    )
    piece = result.scalars().first()
    if not piece:
        raise HTTPException(status_code=404, detail="Content not found")
    if not piece.content_text:
        raise HTTPException(status_code=400, detail="Content has no text")

    # Load top-performing approved/published posts for context
    top_result = await db.execute(
        select(ContentPiece)
        .where(
            ContentPiece.tenant_id == tenant.id,
            ContentPiece.status.in_(["approved", "published", "scheduled"]),
        )
        .limit(10)
    )
    top_posts = top_result.scalars().all()

    original = (piece.content_text or "")[:2000]
    post_len = len(original)
    has_emoji = any(ord(c) > 127 for c in original)
    has_question = "?" in original
    has_list = any(c in original for c in ["1.", "2.", "✅", "→", "•", "-"])
    line_count = original.count("\n")
    first_line = original.split("\n")[0][:100] if original else ""

    # Build reference examples from top posts
    ref_examples = ""
    if top_posts:
        samples = []
        for p in top_posts[:3]:
            txt = (p.content_text or "")[:300]
            samples.append(f'- "{txt}..."')
        ref_examples = "\n".join(samples)
    else:
        ref_examples = "(keine Referenzdaten verfügbar)"

    from services.llm import llm_service

    prompt = (
        "Du bist ein LinkedIn-Engagement-Analyst. Analysiere diesen Post und sag vorher, "
        "wie er performen wird.\n\n"
        f"POST ZUM ANALYSIEREN:\n{original}\n\n"
        f"POST-STATISTIKEN:\n"
        f"- Länge: {post_len} Zeichen\n"
        f"- Emojis: {'Ja' if has_emoji else 'Nein'}\n"
        f"- Frage am Ende: {'Ja' if has_question else 'Nein'}\n"
        f"- Listen/Bullets: {'Ja' if has_list else 'Nein'}\n"
        f"- Zeilen: {line_count}\n"
        f"- Erster Satz: \"{first_line}\"\n\n"
        f"REFERENZ (gut performende Posts dieses Accounts):\n{ref_examples}\n\n"
        "Antworte NUR mit diesem JSON:\n"
        "{\n"
        '  "engagement_score": <0-100>,\n'
        '  "predicted_reach": "<z.B. 500-1.500 Impressionen>",\n'
        '  "predicted_likes": "<z.B. 15-40 Reaktionen>",\n'
        '  "predicted_comments": "<z.B. 3-8 Kommentare>",\n'
        '  "grade": "<A/B/C/D>",\n'
        '  "strengths": ["<Stärke1>", "<Stärke2>"],\n'
        '  "weaknesses": ["<Schwäche1>", "<Schwäche2>"],\n'
        '  "tips": ["<Tipp1 mit konkreter Änderung>", "<Tipp2>", "<Tipp3>"],\n'
        '  "best_post_time": "<z.B. Dienstag 9:00 oder Donnerstag 12:00>",\n'
        '  "hook_score": <0-10>,\n'
        '  "hook_feedback": "<ein Satz über den Hook>"\n'
        "}\n"
        "Sei realistisch und hilfreich. Alle Texte auf Deutsch."
    )

    try:
        raw = await llm_service.complete_json(prompt, purpose="analysis")
        if not isinstance(raw, dict):
            raise HTTPException(status_code=500, detail="LLM returned invalid response")

        return {
            "content_id": content_id,
            "engagement_score": raw.get("engagement_score", 0),
            "predicted_reach": raw.get("predicted_reach", "–"),
            "predicted_likes": raw.get("predicted_likes", "–"),
            "predicted_comments": raw.get("predicted_comments", "–"),
            "grade": raw.get("grade", "C"),
            "strengths": raw.get("strengths") or [],
            "weaknesses": raw.get("weaknesses") or [],
            "tips": raw.get("tips") or [],
            "best_post_time": raw.get("best_post_time", "–"),
            "hook_score": raw.get("hook_score", 0),
            "hook_feedback": raw.get("hook_feedback", ""),
            "post_stats": {
                "chars": post_len,
                "has_emoji": has_emoji,
                "has_question": has_question,
                "has_list": has_list,
                "line_count": line_count,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/content/top-templates")
async def get_top_templates(
    limit: int = 9,
    angle: str | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
):
    """Top-scoring posts as inspiration templates — grouped by angle, no LLM needed."""
    from sqlalchemy import case

    query = select(ContentPiece).where(
        ContentPiece.tenant_id == tenant.id,
        ContentPiece.content_text.isnot(None),
        ContentPiece.channel == "linkedin",
    )
    if angle:
        query = query.where(ContentPiece.content_metadata["angle"].astext == angle)
    # Order: approved first, then by text length as quality proxy (500-1500 chars = good)
    query = query.order_by(
        case({"approved": 0, "published": 0}, value=ContentPiece.status, else_=1).asc(),
        ContentPiece.created_at.desc(),
    ).limit(limit * 3)  # oversample, then client-side score

    result = await db.execute(query)
    pieces = result.scalars().all()

    templates = []
    for p in pieces:
        meta = p.content_metadata or {}
        p_angle = meta.get("angle", "")
        text = p.content_text or ""
        length = len(text)

        # Quick quality score: length 500-1500 + has emoji + has question
        score = 0
        if 400 <= length <= 1600:
            score += 5
        elif length >= 250:
            score += 2
        import re

        if re.search(r"\?", text[-200:]):
            score += 2
        if re.search(r"\p{Emoji}", text, re.UNICODE):
            score += 1
        if text.count("\n\n") >= 2:
            score += 2

        if len(templates) < limit:
            templates.append(
                {
                    "id": str(p.id),
                    "angle": p_angle,
                    "pillar": meta.get("pillar", ""),
                    "preview": text[:200],
                    "full_text": text,
                    "chars": length,
                    "score": score,
                    "status": p.status,
                    "source_name": p.source_name,
                }
            )

    # Sort by score desc
    templates.sort(key=lambda x: x["score"], reverse=True)

    # Collect angle distribution
    angle_counts = {}
    for t in templates:
        a = t["angle"] or "other"
        angle_counts[a] = angle_counts.get(a, 0) + 1

    return {"templates": templates[:limit], "angle_counts": angle_counts, "total": len(pieces)}
