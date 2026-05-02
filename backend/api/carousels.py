"""Carousel API — Generate and download LinkedIn document posts."""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.content_piece import ContentPiece
from models.carousel import CarouselTemplate
from services.carousel_generator import generate_carousel_pdf, split_text_into_slides

router = APIRouter(prefix="/carousels", tags=["carousels"])


class GenerateRequest(BaseModel):
    content_text: Optional[str] = None
    content_piece_id: Optional[str] = None
    slides: Optional[list[dict]] = None
    brand_colors: Optional[dict] = None
    title: str = "LinkedIn Carousel"


@router.post("/generate")
async def generate_carousel(
    data: GenerateRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate a carousel PDF from content text or custom slides."""
    slides = data.slides

    if not slides:
        text = data.content_text
        if not text and data.content_piece_id:
            piece = await db.get(ContentPiece, uuid.UUID(data.content_piece_id))
            if not piece or piece.tenant_id != tenant.id:
                raise HTTPException(404, "Content piece not found")
            text = piece.content_text

        if not text:
            raise HTTPException(400, "content_text, content_piece_id, or slides required")

        slides = split_text_into_slides(text)

    pdf_bytes = generate_carousel_pdf(
        slides=slides,
        brand_colors=data.brand_colors,
        title=data.title,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{data.title}.pdf"'},
    )


@router.post("/preview")
async def preview_carousel(
    data: GenerateRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return slide JSON for preview before generating PDF."""
    text = data.content_text
    if not text and data.content_piece_id:
        piece = await db.get(ContentPiece, uuid.UUID(data.content_piece_id))
        if not piece or piece.tenant_id != tenant.id:
            raise HTTPException(404, "Content piece not found")
        text = piece.content_text

    if not text:
        raise HTTPException(400, "content_text or content_piece_id required")

    slides = data.slides or split_text_into_slides(text)
    return {"slides": slides, "slide_count": len(slides), "title": data.title}


@router.get("/templates")
async def list_templates(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CarouselTemplate).where(
            (CarouselTemplate.tenant_id == tenant.id) | (CarouselTemplate.tenant_id == None)
        ).order_by(CarouselTemplate.is_default.desc())
    )
    templates = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "brand_colors": t.brand_colors,
            "font_config": t.font_config,
            "is_default": t.is_default,
        }
        for t in templates
    ]


# ── Branding CRUD ─────────────────────────────────────────────────────────────

class BrandingUpdate(BaseModel):
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    font_family: Optional[str] = None
    logo_url: Optional[str] = None
    watermark_text: Optional[str] = None


@router.get("/branding")
async def get_branding(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant branding settings."""
    from sqlalchemy import text as _text
    row = (await db.execute(
        _text("SELECT primary_color, secondary_color, font_family, logo_url, watermark_text FROM tenant_branding WHERE tenant_id = :tid"),
        {"tid": str(tenant.id)}
    )).fetchone()
    if not row:
        return {"primary_color": "#0F766E", "secondary_color": "#F59E0B", "font_family": "Helvetica", "logo_url": None, "watermark_text": None}
    return dict(row._mapping)


@router.put("/branding")
async def update_branding(
    data: BrandingUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Upsert tenant branding settings."""
    import re as _re
    from sqlalchemy import text as _text
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "Keine Felder zum Aktualisieren")

    # Validate hex colors
    for color_field in ("primary_color", "secondary_color"):
        if color_field in fields:
            if not _re.match(r'^#[0-9A-Fa-f]{6}$', fields[color_field]):
                raise HTTPException(400, f"{color_field} muss ein 6-stelliger HEX-Code sein (z.B. #0F766E)")

    # Upsert: use defaults for INSERT to avoid NOT NULL violations on partial updates
    await db.execute(
        _text("""INSERT INTO tenant_branding (id, tenant_id, primary_color, secondary_color, font_family, logo_url, watermark_text)
                 VALUES (gen_random_uuid(), :tid,
                   COALESCE(:pc, '#0F766E'),
                   COALESCE(:sc, '#F59E0B'),
                   COALESCE(:ff, 'Helvetica'),
                   :lu, :wt)
                 ON CONFLICT (tenant_id) DO UPDATE SET
                   primary_color = COALESCE(:pc, tenant_branding.primary_color),
                   secondary_color = COALESCE(:sc, tenant_branding.secondary_color),
                   font_family = COALESCE(:ff, tenant_branding.font_family),
                   logo_url = COALESCE(:lu, tenant_branding.logo_url),
                   watermark_text = COALESCE(:wt, tenant_branding.watermark_text),
                   updated_at = NOW()"""),
        {
            "tid": str(tenant.id),
            "pc": fields.get("primary_color"),
            "sc": fields.get("secondary_color"),
            "ff": fields.get("font_family"),
            "lu": fields.get("logo_url"),
            "wt": fields.get("watermark_text"),
        }
    )
    await db.commit()
    return {"status": "ok"}


# ── AI-Carousel Generation ────────────────────────────────────────────────────

class GenerateAIRequest(BaseModel):
    content_piece_id: Optional[str] = None
    post_text: Optional[str] = None
    voice_hint: str = ""
    slide_count: int = 6
    async_mode: bool = False  # True = return task_id, False = block


@router.post("/generate-ai")
async def generate_ai_carousel(
    data: GenerateAIRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI-structured carousel using P12c task."""
    import base64 as _base64
    text_to_use = data.post_text
    if not text_to_use and data.content_piece_id:
        piece = await db.get(ContentPiece, uuid.UUID(data.content_piece_id))
        if not piece or piece.tenant_id != tenant.id:
            raise HTTPException(404, "Content piece not found")
        text_to_use = piece.content_text

    if not text_to_use:
        raise HTTPException(400, "post_text oder content_piece_id erforderlich")

    from tasks.p12c_task import run_p12c
    if data.async_mode:
        task = run_p12c.apply_async(
            args=[str(tenant.id), text_to_use, data.voice_hint, data.content_piece_id],
            kwargs={"slide_count": data.slide_count},
        )
        return {"task_id": task.id, "status": "queued"}
    else:
        result = run_p12c.apply(
            args=[str(tenant.id), text_to_use, data.voice_hint, data.content_piece_id],
            kwargs={"slide_count": data.slide_count},
        ).get()
        if result.get("status") == "failed":
            raise HTTPException(500, result.get("error", "Carousel-Generierung fehlgeschlagen"))
        # Check PDF size if generated
        if "pdf_b64" in result:
            pdf_bytes = _base64.b64decode(result["pdf_b64"])
            if len(pdf_bytes) > 5 * 1024 * 1024:
                raise HTTPException(413, "PDF zu groß (max 5 MB)")
        return {
            "slides": result.get("slides", []),
            "slide_count": result.get("slide_count", 0),
            "carousel_pdf_path": result.get("carousel_pdf_path"),
            "pdf_b64": result.get("pdf_b64"),
        }
