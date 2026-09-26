import pytest
from datetime import datetime, timezone
import uuid
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session, create_engine
from open_skill_registry.server.db.models import (
    Namespace, Skill, SkillVersion, SkillResource, SkillEmbedding, ReleaseTag, ApiKey
)

@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    yield engine

@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session

def test_create_namespace(session: Session):
    ns = Namespace(slug="test-ns", name="Test Namespace")
    session.add(ns)
    session.commit()
    session.refresh(ns)
    
    assert ns.id is not None
    assert ns.slug == "test-ns"
    assert ns.visibility == "PUBLIC"
    assert ns.created_at is not None
    assert ns.updated_at is not None

def test_create_skill(session: Session):
    ns = Namespace(slug="test-ns-2", name="Test")
    session.add(ns)
    session.commit()
    
    skill = Skill(
        namespace_id=ns.id,
        slug="test-skill",
        name="Test Skill",
        tags=["python", "ai"]
    )
    session.add(skill)
    session.commit()
    session.refresh(skill)
    
    assert skill.id is not None
    assert skill.namespace_id == ns.id
    assert skill.tags == ["python", "ai"]
    assert skill.visibility == "PUBLIC"
    assert skill.download_count == 0

def test_create_skill_version(session: Session):
    ns = Namespace(slug="test-ns-3", name="Test")
    session.add(ns)
    session.commit()
    
    skill = Skill(namespace_id=ns.id, slug="test-skill", name="Test")
    session.add(skill)
    session.commit()
    
    version = SkillVersion(
        skill_id=skill.id,
        version="1.0.0",
        content_hash="hash" * 16,
        instructions="test instructions",
        parsed_frontmatter={"key": "value"},
        manifest={"key": "value"},
        compliance_snapshot={},
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    
    assert version.id is not None
    assert version.version == "1.0.0"
    assert version.safety_score == "SAFE"
    assert not version.is_yanked
