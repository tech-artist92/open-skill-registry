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

router = APIRouter(prefix="/api/v1/skills", tags=["skills"])

@router.post("/publish", status_code=201)
async def publish_skill(
    request: Request,
    file: UploadFile = File(...),
    namespace: str = Form("public"),
    slug: Optional[str] = Form(None),
    version: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db_session)
):
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
            explicit_version=version
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
    namespace: Optional[str] = Query(None)
):
    config = getattr(request.app.state, "config", None)
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    
    search_service = SearchService(storage, config)
    results = await search_service.search(query=q, limit=limit, namespace=namespace)
    
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
    namespace: Optional[str] = Query(None)
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    
    page_result = await storage.list_skills(namespace=namespace, page=page, size=size, sort=sort)
    return ResponseEnvelope(data=page_result)

@router.get("/{namespace}/{slug}")
async def get_skill(
    request: Request,
    namespace: str,
    slug: str
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    skill = await storage.get_skill(namespace, slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    
    return ResponseEnvelope(data=skill)

@router.get("/{namespace}/{slug}/versions/{version}")
async def get_skill_version(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    version: str
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    skill = await storage.get_skill(namespace, slug)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
        
    sv = await storage.get_skill_version(namespace, slug, version)
    if not sv:
        raise HTTPException(status_code=404, detail="Version not found")
    
    etag = f'"{sv.content_hash}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
        
    response.headers["ETag"] = etag
    
    return ResponseEnvelope(data={
        "id": str(sv.id),
        "version": sv.version,
        "content_hash": sv.content_hash,
        "manifest": sv.manifest,
        "frontmatter": sv.parsed_frontmatter,
        "compliance_snapshot": sv.compliance_snapshot,
                "tags": await storage.get_version_tags(sv.id)
    })

@router.get("/{namespace}/{slug}/versions/{version}/instructions")
async def get_skill_instructions(
    request: Request,
    response: Response,
    namespace: str,
    slug: str,
    version: str
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    sv = await storage.get_skill_version(namespace, slug, version)
    if not sv:
        raise HTTPException(status_code=404, detail="Version not found")
    
    etag = f'"{sv.content_hash}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
        
    return Response(
        content=sv.instructions or "",
        media_type="text/markdown; charset=utf-8",
        headers={"ETag": etag}
    )

@router.get("/{namespace}/{slug}/versions/{version}/file")
async def get_skill_file(
    request: Request,
    namespace: str,
    slug: str,
    version: str,
    path: str = Query(...)
):
    if ".." in path or path.startswith("/") or "\\" in path:
        raise HTTPException(status_code=400, detail="Invalid path")
        
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    sv = await storage.get_skill_version(namespace, slug, version)
    if not sv:
        raise HTTPException(status_code=404, detail="Version not found")
        
    resource = await storage.get_skill_resource_file(sv.id, path)
    if not resource:
        raise HTTPException(status_code=404, detail="File not found")
        
    return Response(
        content=resource.content,
        media_type=resource.content_type
    )
class TagVersionRequest(BaseModel):
    version: str = Field(..., min_length=1)

@router.put("/{namespace}/{slug}/tags/{tag}")
async def assign_tag(
    request: Request,
    namespace: str,
    slug: str,
    tag: str,
    body: TagVersionRequest
):
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
    namespace: str,
    slug: str,
    tag: str
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    
    sv = await storage.resolve_version(namespace, slug, tag)
    if not sv:
        raise HTTPException(status_code=404, detail="Tag not found or could not be resolved")
        
    return ResponseEnvelope(data={
        "id": str(sv.id),
        "version": sv.version,
        "content_hash": sv.content_hash,
        "manifest": sv.manifest,
        "frontmatter": sv.parsed_frontmatter,
        "compliance_snapshot": sv.compliance_snapshot,
        "tags": await storage.get_version_tags(sv.id)
    })

@router.get("/{namespace}/{slug}/resolve")
async def resolve_skill(
    request: Request,
    namespace: str,
    slug: str,
    hash: Optional[str] = Query(None),
    version: Optional[str] = Query(None),
    tag: Optional[str] = Query(None)
):
    storage = getattr(request.app.state, "storage", None)
    if not storage:
        raise HTTPException(status_code=500, detail="Storage not initialized")
    
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
        
    return ResponseEnvelope(data={
        "namespace": namespace,
        "slug": slug,
        "version": sv.version,
        "content_hash": sv.content_hash,
        "manifest_url": f"/api/v1/skills/{namespace}/{slug}/versions/{sv.version}"
    })
