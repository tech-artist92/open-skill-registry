"""Authentication middleware and FastAPI dependencies (T045)."""

import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import UTC

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from open_skill_registry.server.db.models import ApiKey, Namespace, get_utc_now
from open_skill_registry.server.db.session import get_db_session


@dataclass
class AuthContext:
    """Security context populated for each request."""

    is_authenticated: bool = False
    is_admin: bool = False
    permissions: list[str] = field(default_factory=list)
    namespace_id: uuid.UUID | None = None
    namespace_slug: str | None = None
    key_id: uuid.UUID | None = None


async def get_auth_context(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    """Extract and validate credentials from Authorization header."""
    config = getattr(request.app.state, "config", None)

    auth_enabled = False
    admin_key = os.getenv("OSR_ADMIN_KEY", "")

    if config and hasattr(config, "server"):
        auth_enabled = config.server.auth_enabled
        if not admin_key and config.server.admin_key:
            admin_key = config.server.admin_key

    if not auth_enabled:
        env_auth = os.getenv("OSR_SERVER__AUTH_ENABLED", os.getenv("AUTH_ENABLED", "")).lower()
        if env_auth in ("true", "1", "yes"):
            auth_enabled = True

    # Open Mode: everything allowed as admin
    if not auth_enabled:
        return AuthContext(
            is_authenticated=True,
            is_admin=True,
            permissions=["READ", "WRITE", "ADMIN"],
        )

    # Secured Mode: check Authorization header
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header:
        return AuthContext(is_authenticated=False, is_admin=False, permissions=[])

    parts = auth_header.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected 'Bearer <token>'",
        )

    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    # Check Bootstrap Admin Key
    if admin_key and secrets.compare_digest(token, admin_key):
        return AuthContext(
            is_authenticated=True,
            is_admin=True,
            permissions=["READ", "WRITE", "ADMIN"],
        )

    # Hash and lookup in database
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == token_hash, ApiKey.is_active == True)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    # Check expiry
    now = get_utc_now()
    if api_key.expires_at:
        exp = api_key.expires_at
        if exp.tzinfo is None and now.tzinfo is not None:
            now_cmp = now.replace(tzinfo=None)
        else:
            now_cmp = now
        if exp < now_cmp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired API key",
            )

    # Throttle last_used_at database writes on reads (at most once every 60 seconds)
    should_update_last_used = False
    if api_key.last_used_at is None:
        should_update_last_used = True
    else:
        last_used = api_key.last_used_at
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=UTC)
        if (now - last_used).total_seconds() > 60:
            should_update_last_used = True

    if should_update_last_used:
        api_key.last_used_at = now
        await db.commit()

    # Resolve namespace slug if scoped
    ns_slug = None
    if api_key.namespace_id:
        ns_res = await db.execute(select(Namespace).where(Namespace.id == api_key.namespace_id))
        ns = ns_res.scalar_one_or_none()
        if ns:
            ns_slug = ns.slug

    perms = (
        [p.strip().upper() for p in api_key.permissions.split(",")] if api_key.permissions else []
    )
    is_admin = "ADMIN" in perms and api_key.namespace_id is None

    return AuthContext(
        is_authenticated=True,
        is_admin=is_admin,
        permissions=perms,
        namespace_id=api_key.namespace_id,
        namespace_slug=ns_slug,
        key_id=api_key.id,
    )


def require_admin(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
    """Dependency that requires global admin privileges."""
    if not auth.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return auth


def verify_namespace_write(auth: AuthContext, namespace: str) -> None:
    """Helper to verify caller has write access to target namespace."""
    if not auth.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    if auth.is_admin:
        return
    if auth.namespace_slug != namespace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: API key not authorized for namespace '{namespace}'",
        )
    if "WRITE" not in auth.permissions and "ADMIN" not in auth.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: insufficient permissions for namespace",
        )


def require_namespace_write(
    namespace: str,
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Dependency verifying namespace write permissions."""
    verify_namespace_write(auth, namespace)
    return auth
