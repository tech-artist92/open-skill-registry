import re
from typing import Optional, List

def process_storage(file_path):
    with open(file_path, "r") as f:
        code = f.read()

    # 1. Add get_version_tags
    if "def get_version_tags" not in code:
        get_tags_func = """    async def get_version_tags(self, version_id) -> list[str]:
        from open_skill_registry.server.db.models import ReleaseTag
        from sqlalchemy import select
        async with self.session_maker() as session:
            result = await session.execute(select(ReleaseTag.tag_name).where(ReleaseTag.version_id == version_id))
            return list(result.scalars().all())

    async def get_skill_resources"""
        code = code.replace("    async def get_skill_resources", get_tags_func)
    
    with open(file_path, "w") as f:
        f.write(code)

process_storage("src/open_skill_registry/registry/storage/sqlite.py")
process_storage("src/open_skill_registry/registry/storage/pgvector.py")

with open("src/open_skill_registry/registry/storage/base.py", "r") as f:
    base_code = f.read()
if "get_version_tags" not in base_code:
    get_tags_abs = """    @abstractmethod
    async def get_version_tags(self, version_id: uuid.UUID) -> List[str]:
        pass

    @abstractmethod
    async def get_skill_resources"""
    base_code = base_code.replace("    @abstractmethod\n    async def get_skill_resources", get_tags_abs)
    with open("src/open_skill_registry/registry/storage/base.py", "w") as f:
        f.write(base_code)
