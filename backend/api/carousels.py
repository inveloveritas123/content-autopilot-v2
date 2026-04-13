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
