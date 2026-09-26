from pydantic import BaseModel
from typing import List

class SkillVersion(BaseModel):
    namespace: str
    slug: str
    version: str
    description: str
    tags: List[str]
    created_by: str
