"""Projects API — Multi-project management."""

import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_db, get_tenant
from models.project import Project
from models.source import Source
from models.tenant import Tenant

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


def _slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
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
            "is_default": p.is_default,
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
        "is_default": project.is_default,
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


@router.put("/{project_id}/set-default")
async def set_default_project(
    project_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, uuid.UUID(project_id))
    if not project or project.tenant_id != tenant.id:
        raise HTTPException(404, "Project not found")

    await db.execute(
        update(Project)
        .where(Project.tenant_id == tenant.id, Project.id != uuid.UUID(project_id))
        .values(is_default=False)
    )
    project.is_default = True
    await db.commit()
    return {"updated": True}


@router.post("/{project_id}/duplicate")
async def duplicate_project(
    project_id: str,
    tenant: Tenant = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(Project, uuid.UUID(project_id))
    if not source or source.tenant_id != tenant.id:
        raise HTTPException(404, "Project not found")

    new_id = uuid.uuid4()
    new_name = source.name + " (Kopie)"
    new_slug = _slugify(new_name)

    new_project = Project(
        id=new_id,
        tenant_id=tenant.id,
        name=new_name,
        description=source.description,
        slug=new_slug,
        is_active=source.is_active,
        is_default=False,
    )
    db.add(new_project)
    await db.flush()

    source_id_str = str(source.id)
    new_id_str = str(new_id)

    for tbl in ("tenant_customer_context", "tenant_voice_profile", "tenant_audience_avatar"):
        rows = (
            await db.execute(
                text(
                    f"SELECT version, is_active, source, payload, prompt_version_hash, model_id "
                    f"FROM {tbl} WHERE tenant_id = :tid AND project_id = :pid"
                ),
                {"tid": str(tenant.id), "pid": source_id_str},
            )
        ).fetchall()
        for row in rows:
            await db.execute(
                text(
                    f"INSERT INTO {tbl} "
                    f"(tenant_id, version, is_active, source, payload, prompt_version_hash, model_id, project_id, created_at) "
                    f"VALUES (:tenant_id, :version, :is_active, :source, CAST(:payload AS jsonb), :phash, :model_id, :project_id, now())"
                ),
                {
                    "tenant_id": str(tenant.id),
                    "version": row.version,
                    "is_active": row.is_active,
                    "source": row.source,
                    "payload": json.dumps(row.payload)
                    if not isinstance(row.payload, str)
                    else row.payload,
                    "phash": row.prompt_version_hash,
                    "model_id": row.model_id,
                    "project_id": new_id_str,
                },
            )

    await db.commit()
    return {"id": new_id_str, "name": new_name}
