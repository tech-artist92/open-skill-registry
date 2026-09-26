from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from open_skill_registry.config import RegistryConfig
from open_skill_registry.registry.storage.base import BaseStorage
from open_skill_registry.registry.storage.sqlite import SQLiteStorage
from open_skill_registry.registry.storage.pgvector import PgVectorStorage

def get_storage(config: RegistryConfig, engine: AsyncEngine) -> BaseStorage:
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    
    if config.database.driver == "sqlite":
        return SQLiteStorage(session_maker)
    elif config.database.driver == "postgresql":
        return PgVectorStorage(session_maker)
    else:
        # Default to sqlite if unhandled
        return SQLiteStorage(session_maker)
