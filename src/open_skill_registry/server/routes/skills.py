import io
import zipfile
from typing import Optional, Dict
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from open_skill_registry.server.db.session import get_db_session
from open_skill_registry.server.services.skill_service import SkillService
from open_skill_registry.models.exceptions import DuplicateVersionError

router = APIRouter(prefix="/skills", tags=["skills"])

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
    storage = getattr(request.app.state, "storage", None) # Assuming this is or will be added to app.state

    files: Dict[str, bytes] = {}
    content = await file.read()
    
    if file.filename and file.filename.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                for name in zf.namelist():
                    # Check for path traversal early here too
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
    except DuplicateVersionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"data": {"version": skill_version.version, "slug": skill_version.slug, "namespace": skill_version.namespace}}

# Note: The test for duplicate might need 409 status code. Let's adjust the exception handling.
