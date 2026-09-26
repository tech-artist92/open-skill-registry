"""Initial schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-26 12:00:00.000000

"""
from typing import Sequence, Union
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def get_utc_now():
    return datetime.now(timezone.utc)

def upgrade() -> None:
    # 1. Create vector extension if not exists (Postgres only)
    bind = op.get_bind()
    if bind.engine.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create tables
    op.create_table(
        'namespaces',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('visibility', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_namespaces_slug'), 'namespaces', ['slug'], unique=True)

    op.create_table(
        'skills',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('namespace_id', sa.Uuid(), nullable=False),
        sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('tags', sa.JSON().with_variant(JSONB(), "postgresql"), nullable=True),
        sa.Column('latest_version_id', sa.Uuid(), nullable=True),
        sa.Column('visibility', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('download_count', sa.BigInteger(), nullable=False),
        sa.Column('tsv', sa.Text().with_variant(TSVECTOR(), "postgresql"), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['namespace_id'], ['namespaces.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('namespace_id', 'slug', name='uq_skill_namespace_slug')
    )

    op.create_table(
        'skill_versions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('skill_id', sa.Uuid(), nullable=False),
        sa.Column('version', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('content_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('parsed_frontmatter', sa.JSON(), nullable=True),
        sa.Column('manifest', sa.JSON(), nullable=True),
        sa.Column('compliance_snapshot', sa.JSON(), nullable=True),
        sa.Column('security_scan', sa.JSON(), nullable=True),
        sa.Column('safety_score', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('is_yanked', sa.Boolean(), nullable=False),
        sa.Column('created_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('skill_id', 'version', name='uq_skill_version')
    )

    op.create_foreign_key(
        "fk_skills_latest_version_id",
        "skills",
        "skill_versions",
        ["latest_version_id"],
        ["id"],
        use_alter=True
    )

    op.create_table(
        'skill_resources',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('path', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('content_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('content_hash', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['version_id'], ['skill_versions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('version_id', 'path', name='uq_resource_version_path')
    )

    if bind.engine.name == "postgresql":
        from pgvector.sqlalchemy import Vector
        vector_type = Vector(384)
    else:
        vector_type = sa.Text()

    op.create_table(
        'skill_embeddings',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('source_field', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('embedding', vector_type, nullable=False),
        sa.Column('model_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['version_id'], ['skill_versions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'release_tags',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('skill_id', sa.Uuid(), nullable=False),
        sa.Column('tag_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('version_id', sa.Uuid(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['skill_id'], ['skills.id'], ),
        sa.ForeignKeyConstraint(['version_id'], ['skill_versions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('skill_id', 'tag_name', name='uq_release_tag_skill_tag')
    )

    op.create_table(
        'api_keys',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('key_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('key_prefix', sqlmodel.sql.sqltypes.AutoString(length=8), nullable=False),
        sa.Column('label', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('namespace_id', sa.Uuid(), nullable=True),
        sa.Column('permissions', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['namespace_id'], ['namespaces.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # 3. Add Indexes (Postgres only for GIN/HNSW)
    if bind.engine.name == "postgresql":
        # HNSW on embedding
        op.execute('CREATE INDEX idx_skill_embedding_hnsw ON skill_embeddings USING hnsw (embedding vector_cosine_ops);')
        # GIN on tsv
        op.execute('CREATE INDEX idx_skill_tsv ON skills USING GIN (tsv);')
        # GIN on tags
        op.execute('CREATE INDEX idx_skill_tags ON skills USING GIN (tags);')
    else:
        # SQLite doesn't natively support these specific index types, 
        # we can create standard indices or omit them.
        pass

    # 4. Pre-seed public namespace
    now = get_utc_now()
    public_ns_id = uuid.uuid4()
    op.execute(
        f"""
        INSERT INTO namespaces (id, slug, name, visibility, created_at, updated_at) 
        VALUES ('{public_ns_id}', 'public', 'Public Community Skills', 'PUBLIC', '{now.isoformat()}', '{now.isoformat()}')
        """
    )


def downgrade() -> None:
    # 1. Drop tables
    op.drop_constraint("fk_skills_latest_version_id", "skills", type_="foreignkey")
    op.drop_table('api_keys')
    op.drop_table('release_tags')
    op.drop_table('skill_embeddings')
    op.drop_table('skill_resources')
    op.drop_table('skill_versions')
    op.drop_table('skills')
    op.drop_table('namespaces')
    
    # 2. Drop vector extension
    bind = op.get_bind()
    if bind.engine.name == "postgresql":
        op.execute("DROP EXTENSION IF EXISTS vector;")
