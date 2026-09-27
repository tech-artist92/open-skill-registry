"""API Key management routes (T046)."""

import hashlib
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from open_skill_registry.models.response import ResponseEnvelope
from open_skill_registry.server.db.models import ApiKey, Namespace
from open_skill_registry.server.db.session import get_db_session
from open_skill_registry.server.middleware.auth import AuthContext, require_admin

router = APIRouter(prefix="/api/v1/keys", tags=["auth"])


class CreateKeyRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=128)
    namespace_slug: str | None = None
    namespace_id: uuid.UUID | None = None
    permissions: list[str] | str | None = Field(default_factory=lambda: ["READ", "WRITE"])
    expires_at: datetime | None = None


ALLOWED_PERMISSIONS = {"READ", "WRITE", "ADMIN"}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: CreateKeyRequest,
    db: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_admin),
):
    """Issue a new API key (Admin only)."""
    # Validate permissions
    if body.permissions is None:
        perms_input = ["READ", "WRITE"]
    elif isinstance(body.permissions, str):
        perms_input = [p.strip() for p in body.permissions.split(",") if p.strip()]
    elif isinstance(body.permissions, list):
        perms_input = body.permissions
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Permissions must be a list of strings",
        )

    if not perms_input:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Permissions list cannot be empty",
        )

    perms_list = []
    for p in perms_input:
        if not isinstance(p, str) or p.upper().strip() not in ALLOWED_PERMISSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid permission '{p}'. Allowed permissions are: READ, WRITE, ADMIN",
            )
        perms_list.append(p.upper().strip())

    permissions_str = ",".join(perms_list)

    target_ns_id = body.namespace_id
    ns_slug = body.namespace_slug

    if ns_slug and not target_ns_id:
        ns_res = await db.execute(select(Namespace).where(Namespace.slug == ns_slug))
        ns = ns_res.scalar_one_or_none()
        if not ns:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Namespace '{ns_slug}' not found",
            )
        target_ns_id = ns.id
    elif target_ns_id and not ns_slug:
        ns_res = await db.execute(select(Namespace).where(Namespace.id == target_ns_id))
        ns = ns_res.scalar_one_or_none()
        if ns:
            ns_slug = ns.slug

    # Generate cryptographically secure token
    raw_key = f"osr_live_{secrets.token_hex(20)}"
    key_prefix = raw_key[:12]
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    api_key = ApiKey(
        key_hash=key_hash,
        key_prefix=key_prefix,
        label=body.label,
        namespace_id=target_ns_id,
        permissions=permissions_str,
        expires_at=body.expires_at,
        is_active=True,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ResponseEnvelope(
        code=0,
        data={
            "id": str(api_key.id),
            "raw_key": raw_key,
            "key_prefix": key_prefix,
            "label": api_key.label,
            "namespace_id": str(api_key.namespace_id) if api_key.namespace_id else None,
            "namespace_slug": ns_slug,
            "permissions": perms_list,
            "is_active": api_key.is_active,
            "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
            "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        },
    )


@router.get("")
async def list_api_keys(
    namespace: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_admin),
):
    """List API keys without exposing secrets (Admin only)."""
    stmt = select(ApiKey, Namespace.slug.label("ns_slug")).outerjoin(
        Namespace, ApiKey.namespace_id == Namespace.id
    )

    if namespace:
        stmt = stmt.where(Namespace.slug == namespace)

    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for key, ns_slug in rows:
        perms = [p.strip() for p in key.permissions.split(",")] if key.permissions else []
        items.append(
            {
                "id": str(key.id),
                "key_prefix": key.key_prefix,
                "label": key.label,
                "namespace_id": str(key.namespace_id) if key.namespace_id else None,
                "namespace_slug": ns_slug,
                "permissions": perms,
                "is_active": key.is_active,
                "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
                "created_at": key.created_at.isoformat() if key.created_at else None,
                "expires_at": key.expires_at.isoformat() if key.expires_at else None,
            }
        )

    return ResponseEnvelope(code=0, data=items)


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(require_admin),
):
    """Revoke an API key (Admin only)."""
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    key = result.scalar_one_or_none()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key '{key_id}' not found",
        )

    key.is_active = False
    await db.commit()

    return ResponseEnvelope(
        code=0,
        data={
            "id": str(key.id),
            "is_active": False,
            "revoked": True,
        },
    )
