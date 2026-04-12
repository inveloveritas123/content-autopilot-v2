import uuid
from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.campaign import Campaign
from services.nextcloud import nextcloud_client

router = APIRouter()


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    keywords: list[str] = []
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    nextcloud_folder: Optional[str] = None


@router.get("/campaigns")
async def list_campaigns(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Campaign).where(Campaign.tenant_id == tenant.id).order_by(Campaign.created_at.desc())
    )
    campaigns = result.scalars().all()

    return [
        {
            "id": str(c.id),
            "name": c.name,
            "description": c.description,
            "keywords": c.keywords,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "nextcloud_folder": c.nextcloud_folder,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in campaigns
    ]


@router.post("/campaigns")
async def create_campaign(
    data: CampaignCreate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    campaign = Campaign(
        tenant_id=tenant.id,
        name=data.name,
        description=data.description,
        keywords=data.keywords,
        start_date=data.start_date,
        end_date=data.end_date,
        nextcloud_folder=data.nextcloud_folder,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return {"id": str(campaign.id), "name": campaign.name}


@router.post("/campaigns/sync")
async def sync_campaigns_from_nextcloud(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Sync campaign folders from Nextcloud."""
    folder_path = "/Content-Autopilot/Kampagnen"
    entries = await nextcloud_client.list_folder(folder_path)

    synced = []
    for entry in entries:
        if entry.get("is_directory") and entry.get("name"):
            # Check if campaign already exists
            existing = await db.execute(
                select(Campaign).where(
                    Campaign.tenant_id == tenant.id,
                    Campaign.name == entry["name"],
                )
            )
            if not existing.scalar_one_or_none():
                campaign = Campaign(
                    tenant_id=tenant.id,
                    name=entry["name"],
                    nextcloud_folder=f"{folder_path}/{entry['name']}",
                )
                db.add(campaign)
                synced.append(entry["name"])

    await db.commit()
    return {"synced": synced, "count": len(synced)}
