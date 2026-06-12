"""Content DNA — LinkedIn Post Analysis for Voice Profile."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.content_dna import ContentDNAProfile, ScrapedPost
from models.tenant import Tenant

router = APIRouter(prefix="/content-dna", tags=["content-dna"])


class DNACreateRequest(BaseModel):
    linkedin_url: str | None = None


class PostImportRequest(BaseModel):
    posts: list[dict]  # [{text, likes, comments, shares, post_type, posted_at, hashtags}]


@router.get("/profiles")
async def list_profiles(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ContentDNAProfile).where(ContentDNAProfile.tenant_id == tenant.id)
    )
    profiles = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "linkedin_url": p.linkedin_url,
            "posts_analyzed": p.posts_analyzed,
            "analysis_status": p.analysis_status,
            "voice_attributes": p.voice_attributes,
            "top_topics": p.top_topics,
            "avg_engagement": p.avg_engagement,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in profiles
    ]


@router.post("/profiles")
async def create_profile(
    data: DNACreateRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    profile = ContentDNAProfile(
        tenant_id=tenant.id,
        linkedin_url=data.linkedin_url,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return {"id": str(profile.id), "status": profile.analysis_status}


@router.post("/profiles/{profile_id}/import-posts")
async def import_posts(
    profile_id: str,
    data: PostImportRequest,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Manually import LinkedIn posts for analysis (copy-paste or CSV)."""
    profile = await db.get(ContentDNAProfile, uuid.UUID(profile_id))
    if not profile or profile.tenant_id != tenant.id:
        raise HTTPException(404, "Profile not found")

    imported = 0
    for post_data in data.posts:
        if not post_data.get("text"):
            continue
        post = ScrapedPost(
            dna_profile_id=profile.id,
            text=post_data["text"],
            likes=post_data.get("likes", 0),
            comments=post_data.get("comments", 0),
            shares=post_data.get("shares", 0),
            impressions=post_data.get("impressions"),
            post_type=post_data.get("post_type"),
            hashtags=post_data.get("hashtags", []),
        )
        db.add(post)
        imported += 1

    profile.posts_analyzed = imported
    profile.analysis_status = "imported"
    await db.commit()
    return {"imported": imported, "profile_id": str(profile.id)}


@router.get("/profiles/{profile_id}")
async def get_profile(
    profile_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(ContentDNAProfile, uuid.UUID(profile_id))
    if not profile or profile.tenant_id != tenant.id:
        raise HTTPException(404, "Profile not found")

    posts_result = await db.execute(
        select(ScrapedPost)
        .where(ScrapedPost.dna_profile_id == profile.id)
        .order_by(ScrapedPost.created_at.desc())
    )
    posts = posts_result.scalars().all()

    return {
        "id": str(profile.id),
        "linkedin_url": profile.linkedin_url,
        "posts_analyzed": profile.posts_analyzed,
        "analysis_status": profile.analysis_status,
        "voice_attributes": profile.voice_attributes,
        "top_topics": profile.top_topics,
        "avg_engagement": profile.avg_engagement,
        "posts": [
            {
                "id": str(p.id),
                "text": p.text[:500],
                "likes": p.likes,
                "comments": p.comments,
                "shares": p.shares,
                "post_type": p.post_type,
                "hashtags": p.hashtags,
            }
            for p in posts[:50]
        ],
    }


@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    profile = await db.get(ContentDNAProfile, uuid.UUID(profile_id))
    if not profile or profile.tenant_id != tenant.id:
        raise HTTPException(404, "Profile not found")
    await db.delete(profile)
    await db.commit()
    return {"deleted": True}
