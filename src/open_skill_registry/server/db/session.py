import os
from typing import Optional, AsyncIterator
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker
)
from sqlmodel import SQLModel, select

from .models import Namespace

global_engine: Optional[AsyncEngine] = None
global_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

def get_async_engine(db_url: Optional[str] = None) -> AsyncEngine:
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        
    # Handle "~" in SQLite URLs
    if db_url.startswith("sqlite+aiosqlite:///~"):
        db_url = db_url.replace("~", os.path.expanduser("~"), 1)
        
    connect_args = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        
    engine = create_async_engine(
        db_url,
        echo=False,
        future=True,
        connect_args=connect_args
    )
    return engine

def get_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False
    )

async def init_db(engine: Optional[AsyncEngine] = None) -> None:
    global global_engine
    if engine is None:
        if global_engine is None:
            global_engine = get_async_engine()
        engine = global_engine
        
    async with engine.begin() as conn:
        # Create all tables (useful for embedded mode / tests)
        await conn.run_sync(SQLModel.metadata.create_all)
        
    session_factory = get_session_factory(engine)
    async with session_factory() as session:
        # Pre-seed public namespace
        stmt = select(Namespace).where(Namespace.slug == "public")
        result = await session.execute(stmt)
        public_ns = result.scalar_one_or_none()
        
        if not public_ns:
            public_ns = Namespace(
                id=uuid.uuid4(),
                slug="public",
                name="Public Community Skills",
                visibility="PUBLIC",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            session.add(public_ns)
            await session.commit()

async def get_db_session() -> AsyncIterator[AsyncSession]:
    global global_engine, global_session_factory
    
    if global_engine is None:
        global_engine = get_async_engine()
        
    if global_session_factory is None:
        global_session_factory = get_session_factory(global_engine)
        
    async with global_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

async def close_db() -> None:
    global global_engine, global_session_factory
    
    if global_engine is not None:
        await global_engine.dispose()
        global_engine = None
        global_session_factory = None

