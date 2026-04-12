"""Projects API — Multi-project management."""
import uuid
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.tenant import Tenant
from models.project import Project
from models.source import Source

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug[:100]


@router.get("")
async def list_projects(
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.tenant_id == tenant.id).order_by(Project.created_at)
    )
    projects = result.scalars().all()

    # Get source counts per project
    counts = {}
    for p in projects:
        count_result = await db.execute(
            select(func.count(Source.id)).where(Source.project_id == p.id)
        )
        counts[p.id] = count_result.scalar() or 0

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "slug": p.slug,
            "is_active": p.is_active,
            "source_count": counts.get(p.id, 0),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in projects
    ]


@router.post("")
async def create_project(
    data: ProjectCreate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    project = Project(
        tenant_id=tenant.id,
        name=data.name,
        description=data.description,
        slug=_slugify(data.name),
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return {"id": str(project.id), "name": project.name, "slug": project.slug}


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, uuid.UUID(project_id))
    if not project or project.tenant_id != tenant.id:
        raise HTTPException(404, "Project not found")
    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "slug": project.slug,
        "is_active": project.is_active,
    }


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, uuid.UUID(project_id))
    if not project or project.tenant_id != tenant.id:
        raise HTTPException(404, "Project not found")
    if data.name is not None:
        project.name = data.name
        project.slug = _slugify(data.name)
    if data.description is not None:
        project.description = data.description
    if data.is_active is not None:
        project.is_active = data.is_active
    await db.commit()
    return {"updated": True}


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, uuid.UUID(project_id))
    if not project or project.tenant_id != tenant.id:
        raise HTTPException(404, "Project not found")
    await db.delete(project)
    await db.commit()
    return {"deleted": True}
