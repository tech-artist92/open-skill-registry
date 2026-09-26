"""Namespace CRUD and discovery routes (T047)."""


from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from open_skill_registry.models.response import Page, ResponseEnvelope
from open_skill_registry.server.db.models import Namespace, Skill, get_utc_now
from open_skill_registry.server.db.session import get_db_session
from open_skill_registry.server.middleware.auth import (
    AuthContext,
    get_auth_context,
    require_admin,
)

router = APIRouter(prefix="/api/v1/namespaces", tags=["namespaces"])


class CreateNamespaceRequest(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    visibility: str = Field(default="PUBLIC")


class UpdateNamespaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    visibility: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_namespace(
    body: CreateNamespaceRequest,
    db: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_admin),
):
    """Create a new namespace (Admin only)."""
    # Check uniqueness
    existing_res = await db.execute(select(Namespace).where(Namespace.slug == body.slug))
    if existing_res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Namespace '{body.slug}' already exists",
        )

    visibility = body.visibility.upper()
    if visibility not in ("PUBLIC", "NAMESPACE_ONLY", "PRIVATE"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid visibility '{body.visibility}'. "
                "Must be PUBLIC, NAMESPACE_ONLY, or PRIVATE"
            ),
        )

    ns = Namespace(
        slug=body.slug,
        name=body.name,
        description=body.description,
        visibility=visibility,
    )
    db.add(ns)
    await db.commit()
    await db.refresh(ns)

    return ResponseEnvelope(
        code=0,
        data={
            "id": str(ns.id),
            "slug": ns.slug,
            "name": ns.name,
            "description": ns.description,
            "visibility": ns.visibility,
            "created_at": ns.created_at.isoformat() if ns.created_at else None,
            "updated_at": ns.updated_at.isoformat() if ns.updated_at else None,
        },
    )


@router.get("")
async def list_namespaces(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_auth_context),
):
    """List namespaces with visibility filtering."""
    stmt = select(Namespace)

    if not auth.is_admin:
        if auth.is_authenticated and auth.namespace_slug:
            stmt = stmt.where(
                or_(
                    Namespace.visibility == "PUBLIC",
                    Namespace.slug == auth.namespace_slug,
                )
            )
        else:
            stmt = stmt.where(Namespace.visibility == "PUBLIC")

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.order_by(Namespace.slug.asc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    namespaces = result.scalars().all()

    items = [
        {
            "id": str(ns.id),
            "slug": ns.slug,
            "name": ns.name,
            "description": ns.description,
            "visibility": ns.visibility,
            "created_at": ns.created_at.isoformat() if ns.created_at else None,
            "updated_at": ns.updated_at.isoformat() if ns.updated_at else None,
        }
        for ns in namespaces
    ]

    return ResponseEnvelope(
        code=0,
        data=Page(
            items=items,
            total=total,
            page=page,
            page_size=size,
        ),
    )


@router.get("/{slug}")
async def get_namespace(
    slug: str,
    db: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_auth_context),
):
    """Get namespace details including skill count."""
    res = await db.execute(select(Namespace).where(Namespace.slug == slug))
    ns = res.scalar_one_or_none()
    if not ns:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Namespace '{slug}' not found",
        )

    # Visibility check
    if ns.visibility != "PUBLIC" and not auth.is_admin and auth.namespace_slug != slug:
        if not auth.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: insufficient permissions for namespace",
        )

    count_res = await db.execute(select(func.count(Skill.id)).where(Skill.namespace_id == ns.id))
    skill_count = count_res.scalar() or 0

    return ResponseEnvelope(
        code=0,
        data={
            "id": str(ns.id),
            "slug": ns.slug,
            "name": ns.name,
            "description": ns.description,
            "visibility": ns.visibility,
            "skill_count": skill_count,
            "created_at": ns.created_at.isoformat() if ns.created_at else None,
            "updated_at": ns.updated_at.isoformat() if ns.updated_at else None,
        },
    )


@router.put("/{slug}")
async def update_namespace(
    slug: str,
    body: UpdateNamespaceRequest,
    db: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_auth_context),
):
    """Update namespace settings."""
    if not auth.is_admin and not (auth.namespace_slug == slug and "ADMIN" in auth.permissions):
        if not auth.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: admin permissions required for this namespace",
        )

    res = await db.execute(select(Namespace).where(Namespace.slug == slug))
    ns = res.scalar_one_or_none()
    if not ns:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Namespace '{slug}' not found",
        )

    if body.name is not None:
        ns.name = body.name
    if body.description is not None:
        ns.description = body.description
    if body.visibility is not None:
        vis = body.visibility.upper()
        if vis not in ("PUBLIC", "NAMESPACE_ONLY", "PRIVATE"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid visibility '{body.visibility}'. "
                    "Must be PUBLIC, NAMESPACE_ONLY, or PRIVATE"
                ),
            )
        ns.visibility = vis

    ns.updated_at = get_utc_now()
    await db.commit()
    await db.refresh(ns)

    return ResponseEnvelope(
        code=0,
        data={
            "id": str(ns.id),
            "slug": ns.slug,
            "name": ns.name,
            "description": ns.description,
            "visibility": ns.visibility,
            "created_at": ns.created_at.isoformat() if ns.created_at else None,
            "updated_at": ns.updated_at.isoformat() if ns.updated_at else None,
        },
    )
