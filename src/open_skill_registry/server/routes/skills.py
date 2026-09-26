import io
import zipfile
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
from fastapi import Query, Response
from fastapi.responses import PlainTextResponse
from open_skill_registry.server.services.search_service import SearchService
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from open_skill_registry.server.db.session import get_db_session
from open_skill_registry.server.services.skill_service import SkillService
from open_skill_registry.models.exceptions import DuplicateVersionError
from open_skill_registry.models.response import ResponseEnvelope
from open_skill_registry.server.middleware.auth import (
    AuthContext,
    get_auth_context,
    verify_namespace_write,
)

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])


ALLOWED_VISIBILITIES = {"PUBLIC", "NAMESPACE_ONLY", "PRIVATE"}


def check_skill_read_permission(skill, namespace: str, auth: AuthContext) -> None:
    """Ensure caller has permission to view skill."""
    if getattr(skill, "visibility", "PUBLIC") != "PUBLIC":
        if not auth.is_authenticated:
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
            )
        if auth.is_admin:
            return
        if auth.namespace_slug != namespace:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: insufficient permissions for namespace",
            )
        if "READ" not in auth.permissions and "ADMIN" not in auth.permissions:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: insufficient permissions for namespace",
            )

@router.post("/publish", status_code=201)
async def publish_skill(
    request: Request,
    file: UploadFile = File(...),
    namespace: str = Form("public"),
    slug: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    visibility: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_session),
    auth: AuthContext = Depends(get_auth_context),
):
    verify_namespace_write(auth, namespace)

    if visibility is not None:
        visibility = visibility.upper().strip()
        if not visibility:
            visibility = None
        elif visibility not in ALLOWED_VISIBILITIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid visibility '{visibility}'. Must be one of: PUBLIC, NAMESPACE_ONLY, PRIVATE",
            )

    config = getattr(request.app.state, "config", None)
    storage = getattr(request.app.state, "storage", None)
    if storage is None and config:
        from open_skill_registry.registry.storage.factory import get_storage
        import open_skill_registry.server.db.session as db_session
        storage = get_storage(config, db_session.global_engine)

    files: Dict[str, bytes] = {}
    content = await file.read()
    
    if file.filename and file.filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    if ".." in name or name.startswith("/"):
                        raise HTTPException(status_code=400, detail="Path traversal detected in zip")
                    if not zf.getinfo(name).is_dir():
                        files[name] = zf.read(name)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid zip archive")
    else:
        filename = file.filename or "SKILL.md"
        files[filename] = content
        
    service = SkillService(db, storage, config)
    
    try:
        skill_version = await service.publish_skill(
            namespace=namespace,
            files=files,
            explicit_slug=slug,
            explicit_version=version,
            visibility=visibility,
        )
        final_slug = slug
        if not final_slug:
            frontmatter = service._parse_frontmatter(files.get("SKILL.md", b""))
            final_slug = frontmatter.get("slug") or service._slugify(frontmatter.get("name", "untitled"))
    except DuplicateVersionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    return ResponseEnvelope(
        code=0,
        msg="success",
        data={
            "namespace": namespace,
            "slug": final_slug,
            "version": skill_version.version,
            "content_hash": getattr(skill_version, "content_hash", "")
        }
    )


@router.get("/search")
async def search_skills(
    request: Request,
    q: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    namespace: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth_context),
):
    config = getattr(request.app.state, "config", None)
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    
    has_read = "READ" in auth.permissions or "ADMIN" in auth.permissions
    allowed_namespaces = (
        [auth.namespace_slug]
        if (auth.is_authenticated and auth.namespace_slug and has_read)
        else ([] if not auth.is_admin else None)
    )
    search_service = SearchService(storage, config)
    results = await search_service.search(
        query=q,
        limit=limit,
        namespace=namespace,
        allowed_namespaces=allowed_namespaces,
        is_admin=auth.is_admin,
    )
    
    # Standard envelope expects items in data
    # But brief says: Data has `items` and `total`
    items = []
    for r in results:
        item = r["item"].model_dump()
        item["similarity_score"] = r["score"]
        items.append(item)
    
    return ResponseEnvelope(
        data={"items": items, "total": len(items)}
    )

@router.get("")
async def list_skills(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    sort: str = Query("updated"),
    namespace: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth_context),
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    
    has_read = "READ" in auth.permissions or "ADMIN" in auth.permissions
    allowed_namespaces = (
        [auth.namespace_slug]
        if (auth.is_authenticated and auth.namespace_slug and has_read)
        else ([] if not auth.is_admin else None)
    )
    page_result = await storage.list_skills(
        namespace=namespace,
        page=page,
        size=size,
        sort=sort,
        allowed_namespaces=allowed_namespaces,
        is_admin=auth.is_admin,
    )
    return ResponseEnvelope(data=page_result)

@router.get("/{namespace}/{slug}")
async def get_skill(
    request: Request,
    namespace: str,
    slug: str,
    auth: AuthContext = Depends(get_auth_context),
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    skill = await storage.get_skill(namespace, slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    check_skill_read_permission(skill, namespace, auth)
    
    return ResponseEnvelope(data=skill)

@router.delete("/{namespace}/{slug}/versions/{version}")
async def yank_skill_version(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    auth: AuthContext = Depends(get_auth_context),
):
    verify_namespace_write(auth, namespace)
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")

    skill = await storage.get_skill(namespace, slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    sv = await storage.get_skill_version(namespace, slug, version)
    if not sv:
        raise HTTPException(status_code=404, detail="Version not found")

    try:
        await storage.yank_version(namespace, slug, version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ResponseEnvelope(
        code=200,
        message=f"Version {version} of skill {namespace}/{slug} has been yanked",
        data={
            "namespace": namespace,
            "slug": slug,
            "version": version,
            "is_yanked": True,
        },
    )


@router.get("/{namespace}/{slug}/versions/{version}")
async def get_skill_version(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    version: str,
    auth: AuthContext = Depends(get_auth_context),
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    skill = await storage.get_skill(namespace, slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    check_skill_read_permission(skill, namespace, auth)

    sv = await storage.get_skill_version(namespace, slug, version)
    if not sv:
        raise HTTPException(status_code=404, detail="Version not found")

    if sv.is_yanked:
        response.headers["X-Skill-Warning"] = "Yanked"

    etag = f'"{sv.content_hash}"'
    if request.headers.get("if-none-match") == etag:
        headers = {"ETag": etag}
        if sv.is_yanked:
            headers["X-Skill-Warning"] = "Yanked"
        return Response(status_code=304, headers=headers)

    response.headers["ETag"] = etag

    return ResponseEnvelope(data={
        "id": str(sv.id),
        "version": sv.version,
        "content_hash": sv.content_hash,
        "manifest": sv.manifest,
        "frontmatter": sv.parsed_frontmatter,
        "compliance_snapshot": sv.compliance_snapshot,
        "tags": await storage.get_version_tags(sv.id),
        "is_yanked": sv.is_yanked,
        "yanked": sv.is_yanked,
    })


async def _fetch_instructions(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    version: Optional[str],
    auth: AuthContext,
) -> Response:
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    skill = await storage.get_skill(namespace, slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    check_skill_read_permission(skill, namespace, auth)

    if version:
        sv = await storage.get_skill_version(namespace, slug, version)
    else:
        sv = await storage.resolve_version(namespace, slug, "latest")

    if not sv:
        raise HTTPException(status_code=404, detail="Version not found")

    etag = f'"{sv.content_hash}"'
    headers = {"ETag": etag}
    if sv.is_yanked:
        headers["X-Skill-Warning"] = "Yanked"
        response.headers["X-Skill-Warning"] = "Yanked"

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    return Response(
        content=sv.instructions or "",
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )


@router.get("/{namespace}/{slug}/instructions")
async def get_skill_instructions_query(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    version: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth_context),
):
    return await _fetch_instructions(request, response, namespace, slug, version, auth)


@router.get("/{namespace}/{slug}/versions/{version}/instructions")
async def get_skill_instructions(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    version: str,
    auth: AuthContext = Depends(get_auth_context),
):
    return await _fetch_instructions(request, response, namespace, slug, version, auth)


async def _fetch_file(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    version: Optional[str],
    path: str,
    auth: AuthContext,
) -> Response:
    if ".." in path or path.startswith("/") or "\\" in path:
        raise HTTPException(status_code=400, detail="Invalid path")

    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    skill = await storage.get_skill(namespace, slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    check_skill_read_permission(skill, namespace, auth)

    if version:
        sv = await storage.get_skill_version(namespace, slug, version)
    else:
        sv = await storage.resolve_version(namespace, slug, "latest")

    if not sv:
        raise HTTPException(status_code=404, detail="Version not found")

    resource = await storage.get_skill_resource_file(sv.id, path)
    if not resource:
        raise HTTPException(status_code=404, detail="File not found")

    headers = {}
    if sv.is_yanked:
        headers["X-Skill-Warning"] = "Yanked"
        response.headers["X-Skill-Warning"] = "Yanked"

    return Response(
        content=resource.content,
        media_type=resource.content_type,
        headers=headers,
    )


@router.get("/{namespace}/{slug}/file")
async def get_skill_file_query(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    path: str = Query(...),
    version: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth_context),
):
    return await _fetch_file(request, response, namespace, slug, version, path, auth)


@router.get("/{namespace}/{slug}/versions/{version}/file")
async def get_skill_file(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    version: str,
    path: str = Query(...),
    auth: AuthContext = Depends(get_auth_context),
):
    return await _fetch_file(request, response, namespace, slug, version, path, auth)

class TagVersionRequest(BaseModel):
    version: str = Field(..., min_length=1)

@router.put("/{namespace}/{slug}/tags/{tag}")
async def assign_tag(
    request: Request,
    namespace: str,
    slug: str,
    tag: str,
    body: TagVersionRequest,
    auth: AuthContext = Depends(get_auth_context),
):
    verify_namespace_write(auth, namespace)
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    
    try:
        await storage.tag_version(namespace, slug, body.version, tag)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    return ResponseEnvelope(
        code=0,
        msg="success",
        data={
            "namespace": namespace,
            "slug": slug,
            "tag": tag,
            "version": body.version
        }
    )

@router.get("/{namespace}/{slug}/tags/{tag}")
async def get_tag_shortcut(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    tag: str,
    auth: AuthContext = Depends(get_auth_context),
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    skill = await storage.get_skill(namespace, slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    check_skill_read_permission(skill, namespace, auth)

    sv = await storage.resolve_version(namespace, slug, tag)
    if not sv:
        raise HTTPException(status_code=404, detail="Tag not found or could not be resolved")

    if sv.is_yanked:
        response.headers["X-Skill-Warning"] = "Yanked"

    return ResponseEnvelope(data={
        "id": str(sv.id),
        "version": sv.version,
        "content_hash": sv.content_hash,
        "manifest": sv.manifest,
        "frontmatter": sv.parsed_frontmatter,
        "compliance_snapshot": sv.compliance_snapshot,
        "tags": await storage.get_version_tags(sv.id),
        "is_yanked": sv.is_yanked,
        "yanked": sv.is_yanked,
    })

@router.get("/{namespace}/{slug}/resolve")
async def resolve_skill(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    hash: Optional[str] = Query(None),
    version: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    auth: AuthContext = Depends(get_auth_context),
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    skill = await storage.get_skill(namespace, slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    check_skill_read_permission(skill, namespace, auth)

    sv = None
    if hash:
        sv = await storage.resolve_by_hash(namespace, slug, hash)
    elif version:
        sv = await storage.get_skill_version(namespace, slug, version)
    else:
        resolved_tag = tag or "latest"
        sv = await storage.resolve_version(namespace, slug, resolved_tag)
        
    if not sv:
        raise HTTPException(status_code=404, detail="Could not resolve version")

    if sv.is_yanked:
        response.headers["X-Skill-Warning"] = "Yanked"

    return ResponseEnvelope(data={
        "namespace": namespace,
        "slug": slug,
        "version": sv.version,
        "content_hash": sv.content_hash,
        "manifest_url": f"/api/v1/skills/{namespace}/{slug}/versions/{sv.version}",
        "is_yanked": sv.is_yanked,
    })

