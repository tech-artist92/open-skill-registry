import json

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from open_skill_registry.server.db.models import (
    ApiKey,
    Namespace,
    ReleaseTag,
    Skill,
    SkillEmbedding,
    SkillResource,
    SkillVersion,
    VectorType,
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

def test_create_all_models(session: Session):
    # Namespace
    ns = Namespace(slug="test-ns", name="Test Namespace")
    session.add(ns)
    session.commit()
    
    # Skill
    skill = Skill(
        namespace_id=ns.id,
        slug="test-skill",
        name="Test Skill",
        tags=["python", "ai"]
    )
    session.add(skill)
    session.commit()
    
    # SkillVersion
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

    # Update latest_version_id
    skill.latest_version_id = version.id
    session.add(skill)
    session.commit()

    # SkillResource
    resource = SkillResource(
        version_id=version.id,
        path="main.py",
        content_type="text/x-python",
        content=b"print('hello')",
        content_hash="hash_rsc",
        size_bytes=14
    )
    session.add(resource)
    session.commit()

    # SkillEmbedding
    embedding = SkillEmbedding(
        version_id=version.id,
        source_field="instructions",
        embedding=[0.1] * 384,
        model_name="test-model"
    )
    session.add(embedding)
    session.commit()

    # ReleaseTag
    tag = ReleaseTag(
        skill_id=skill.id,
        tag_name="latest",
        version_id=version.id
    )
    session.add(tag)
    session.commit()

    # ApiKey
    api_key = ApiKey(
        key_hash="hash_key",
        key_prefix="prefix_",
        label="test key",
        permissions="READ"
    )
    session.add(api_key)
    session.commit()
    
    # Verify records
    assert session.exec(select(Namespace)).first().id == ns.id
    assert session.exec(select(Skill)).first().id == skill.id
    assert session.exec(select(SkillVersion)).first().id == version.id
    assert session.exec(select(SkillResource)).first().id == resource.id
    assert session.exec(select(SkillEmbedding)).first().id == embedding.id
    assert session.exec(select(ReleaseTag)).first().id == tag.id
    assert session.exec(select(ApiKey)).first().id == api_key.id

def test_unique_constraints(session: Session):
    ns = Namespace(slug="unique-ns", name="Namespace 1")
    session.add(ns)
    session.commit()

    # Duplicate namespace slug
    ns2 = Namespace(slug="unique-ns", name="Namespace 2")
    session.add(ns2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    skill = Skill(namespace_id=ns.id, slug="unique-skill", name="Skill 1")
    session.add(skill)
    session.commit()

    # Duplicate skill slug in same namespace
    skill2 = Skill(namespace_id=ns.id, slug="unique-skill", name="Skill 2")
    session.add(skill2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

def test_vector_type_serialization():
    from unittest.mock import Mock
    
    # Test SQLite (fallback)
    vector_type = VectorType(dim=384)
    sqlite_dialect = Mock(name="sqlite")
    
    # Bind (list to string)
    bound_val = vector_type.process_bind_param([0.1, 0.2, 0.3], sqlite_dialect)
    assert isinstance(bound_val, str)
    assert json.loads(bound_val) == [0.1, 0.2, 0.3]
    
    # Result (string to list)
    result_val = vector_type.process_result_value(bound_val, sqlite_dialect)
    assert isinstance(result_val, list)
    assert result_val == [0.1, 0.2, 0.3]
