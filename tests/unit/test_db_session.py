import os

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlmodel import select

from open_skill_registry.server.db.models import Namespace
from open_skill_registry.server.db.session import (
    close_db,
    get_async_engine,
    get_db_session,
    get_session_factory,
    init_db,
)


@pytest.mark.asyncio
async def test_get_async_engine():
    engine = get_async_engine("sqlite+aiosqlite:///:memory:")
    assert isinstance(engine, AsyncEngine)
    await engine.dispose()

@pytest.mark.asyncio
async def test_sqlite_tilde_expansion():
    # It should expand ~ to user home
    engine = get_async_engine("sqlite+aiosqlite:///~/registry.db")
    home = os.path.expanduser("~")
    assert str(engine.url) == f"sqlite+aiosqlite:///{home}/registry.db"
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
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    
    
    # Ensure starting clean
    await close_db()
    
    # get_db_session will call get_async_engine() internally
    # But since we need tables created, we call init_db with None
    await init_db()
    
    gen = get_db_session()
    session = await anext(gen)
    
    assert isinstance(session, AsyncSession)
    
    # Verify we can query the public namespace seeded by init_db (proves engine reuse)
    result = await session.execute(select(Namespace).where(Namespace.slug == "public"))
    ns = result.scalar_one_or_none()
    assert ns is not None
    assert ns.name == "Public Community Skills"
    
    # Clean up
    await gen.aclose()
    await close_db()
