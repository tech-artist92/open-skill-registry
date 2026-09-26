from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import Dict, Any

from open_skill_registry.models.response import ResponseEnvelope
from open_skill_registry.server.db.session import get_db_session

router = APIRouter()

@router.get("/health", response_model=ResponseEnvelope[Dict[str, str]])
async def health_check(request: Request, db: AsyncSession = Depends(get_db_session)):
    app = request.app
    cache_service = getattr(app.state, "cache_service", None)
    config = getattr(app.state, "config", None)
    
    # DB Status
    db_status = "error"
    try:
        await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "error"
        
    # Cache Status
    redis_status = "disabled"
    if cache_service:
        if not cache_service.config.enabled:
            redis_status = "disabled"
        elif cache_service._use_redis:
            try:
                await cache_service._redis.ping()
                redis_status = "connected"
            except Exception:
                redis_status = "error"
        else:
            redis_status = "in-memory"

    # Embedding Provider Identifier
    # The config has embedding_provider and embedding_model.
    embeddings_status = "unknown"
    if config:
        search_config = getattr(config, "search", None)
        if search_config:
            provider = getattr(search_config, "provider", "fastembed")
            model = getattr(search_config, "model", "BAAI/bge-small-en-v1.5")
        else:
            provider = "fastembed"
            model = "BAAI/bge-small-en-v1.5"
            
        if not model:
            if provider == "fastembed":
                model = "BAAI/bge-small-en-v1.5"
            else:
                model = "default"
        embeddings_status = f"{provider} ({model})"

    return ResponseEnvelope(
        code=0,
        data={
            "status": "ok",
            "db": db_status,
            "redis": redis_status,
            "embeddings": embeddings_status
        }
    )
