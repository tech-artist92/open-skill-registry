import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel, select

from .models import Namespace

global_engine: AsyncEngine | None = None
global_session_factory: async_sessionmaker[AsyncSession] | None = None

def get_async_engine(db_url: str | None = None) -> AsyncEngine:
    if db_url is None:
        db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        
    # Ensure async driver dialects
    if db_url.startswith("sqlite:/") and "sqlite+aiosqlite" not in db_url:
        db_url = db_url.replace("sqlite:", "sqlite+aiosqlite:", 1)
    elif db_url.startswith("postgresql:/") and "postgresql+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql:", "postgresql+asyncpg:", 1)
    elif db_url.startswith("postgres:/") and "postgresql+asyncpg" not in db_url:
        db_url = db_url.replace("postgres:", "postgresql+asyncpg:", 1)

    # Handle "~" in SQLite URLs
    if ":///~" in db_url:
        db_url = db_url.replace("~", os.path.expanduser("~"), 1)

    if db_url.startswith("sqlite+aiosqlite:///") and not db_url.startswith("sqlite+aiosqlite:///:memory:"):
        file_path = db_url.replace("sqlite+aiosqlite:///", "", 1)
        dir_name = os.path.dirname(os.path.abspath(file_path))
        if dir_name:
            try:
                os.makedirs(dir_name, exist_ok=True)
            except (PermissionError, OSError):
                pass
        
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

async def init_db(engine: AsyncEngine | None = None) -> None:
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
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC)
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

