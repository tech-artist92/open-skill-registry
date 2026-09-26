import pytest
import os
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine
from open_skill_registry.server.db.session import (
    get_async_engine,
    get_session_factory,
    init_db,
    get_db_session
)
from open_skill_registry.server.db.models import Namespace
from sqlmodel import select

@pytest.mark.asyncio
async def test_get_async_engine():
    engine = get_async_engine("sqlite+aiosqlite:///:memory:")
    assert isinstance(engine, AsyncEngine)
    await engine.dispose()

@pytest.mark.asyncio
async def test_init_db_and_session_factory():
    engine = get_async_engine("sqlite+aiosqlite:///:memory:")
    
    # Initialize DB (creates tables and public namespace)
    await init_db(engine)
    
    async_session = get_session_factory(engine)
    
    async with async_session() as session:
        # Check if public namespace was seeded
        result = await session.execute(select(Namespace).where(Namespace.slug == "public"))
        ns = result.scalar_one_or_none()
        
        assert ns is not None
        assert ns.name == "Public Community Skills"
        assert ns.visibility == "PUBLIC"
        
    await engine.dispose()

@pytest.mark.asyncio
async def test_get_db_session_dependency():
    # Since we can't easily mock the global engine for the dependency in a simple way here,
    # we just ensure the generator yields an AsyncSession
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    
    from open_skill_registry.server.db import session as db_session_module
    # re-init to use memory
    db_session_module.global_engine = get_async_engine("sqlite+aiosqlite:///:memory:")
    db_session_module.global_session_factory = get_session_factory(db_session_module.global_engine)
    
    await init_db(db_session_module.global_engine)
    
    gen = get_db_session()
    session = await anext(gen)
    
    assert isinstance(session, AsyncSession)
    
    # Clean up
    await gen.aclose()
    await db_session_module.global_engine.dispose()
