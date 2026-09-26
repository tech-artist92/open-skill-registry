import json
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, UniqueConstraint, Index, ForeignKey
from sqlalchemy.types import TypeDecorator, Text, JSON, BigInteger, Boolean, LargeBinary, String, DateTime
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlmodel import SQLModel, Field
import sqlmodel.sql.sqltypes

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False

class VectorType(TypeDecorator):
    impl = Text
    cache_ok = True

    def __init__(self, dim: int, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and HAS_PGVECTOR:
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql" and HAS_PGVECTOR:
            return value
        if isinstance(value, list):
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql" and HAS_PGVECTOR:
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value

def get_utc_now():
    return datetime.now(timezone.utc)

class Namespace(SQLModel, table=True):
    __tablename__ = "namespaces"
    __table_args__ = {"extend_existing": True}
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    slug: str = Field(max_length=64, unique=True, index=True)
    name: str
    description: Optional[str] = Field(default=None)
    visibility: str = Field(default="PUBLIC")
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

class Skill(SQLModel, table=True):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("namespace_id", "slug", name="uq_skill_namespace_slug"),
        {"extend_existing": True}
    )
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    namespace_id: uuid.UUID = Field(foreign_key="namespaces.id")
    slug: str = Field(max_length=64)
    name: str
    description: Optional[str] = Field(default=None)
    tags: List[str] = Field(default_factory=list, sa_column=Column(JSON().with_variant(JSONB, "postgresql")))
    latest_version_id: Optional[uuid.UUID] = Field(default=None, sa_column_args=[ForeignKey("skill_versions.id", use_alter=True)])
    visibility: str = Field(default="PUBLIC")
    download_count: int = Field(default=0, sa_column=Column(BigInteger))
    tsv: Optional[str] = Field(default=None, sa_column=Column(Text().with_variant(TSVECTOR, "postgresql")))
    created_at: datetime = Field(default_factory=get_utc_now)
    updated_at: datetime = Field(default_factory=get_utc_now)

class SkillVersion(SQLModel, table=True):
    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint("skill_id", "version", name="uq_skill_version"),
        {"extend_existing": True}
    )
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    skill_id: uuid.UUID = Field(foreign_key="skills.id")
    version: str
    content_hash: str = Field(max_length=64)
    instructions: str = Field(sa_column=Column(Text))
    parsed_frontmatter: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    manifest: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    compliance_snapshot: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    security_scan: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    safety_score: str = Field(default="SAFE")
    is_yanked: bool = Field(default=False)
    created_by: str = Field(default="system")
    created_at: datetime = Field(default_factory=get_utc_now)

class SkillResource(SQLModel, table=True):
    __tablename__ = "skill_resources"
    __table_args__ = (
        UniqueConstraint("version_id", "path", name="uq_resource_version_path"),
        {"extend_existing": True}
    )
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    version_id: uuid.UUID = Field(foreign_key="skill_versions.id")
    path: str
    content_type: str
    content: bytes = Field(sa_column=Column(LargeBinary))
    content_hash: str = Field(max_length=64)
    size_bytes: int
    created_at: datetime = Field(default_factory=get_utc_now)

class SkillEmbedding(SQLModel, table=True):
    __tablename__ = "skill_embeddings"
    __table_args__ = {"extend_existing": True}
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    version_id: uuid.UUID = Field(foreign_key="skill_versions.id")
    source_field: str
    embedding: List[float] = Field(sa_column=Column(VectorType(384)))
    model_name: str
    created_at: datetime = Field(default_factory=get_utc_now)

class ReleaseTag(SQLModel, table=True):
    __tablename__ = "release_tags"
    __table_args__ = (
        UniqueConstraint("skill_id", "tag_name", name="uq_release_tag_skill_tag"),
        {"extend_existing": True}
    )
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    skill_id: uuid.UUID = Field(foreign_key="skills.id")
    tag_name: str
    version_id: uuid.UUID = Field(foreign_key="skill_versions.id")
    updated_at: datetime = Field(default_factory=get_utc_now)

class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"
    __table_args__ = {"extend_existing": True}
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    key_hash: str
    key_prefix: str = Field(max_length=8)
    label: str
    namespace_id: Optional[uuid.UUID] = Field(default=None, foreign_key="namespaces.id")
    permissions: str
    is_active: bool = Field(default=True)
    expires_at: Optional[datetime] = Field(default=None)
    last_used_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=get_utc_now)
