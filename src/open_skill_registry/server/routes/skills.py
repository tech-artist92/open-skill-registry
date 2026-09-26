import io
import zipfile
from typing import Optional, Dict
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
