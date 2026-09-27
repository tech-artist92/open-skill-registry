
import pytest

from open_skill_registry.adk import (
    AuthenticationError,
    Frontmatter,
    OpenSkillRegistry,
    Skill,
    SkillNotFoundError,
)

# Mocks for testing

@pytest.fixture
def mock_sync_registry():
    class MockSyncRegistry:
        def __init__(self):
            self.skills = {
                "public/test-skill": {
                    "name": "public/test-skill",
                    "description": "A test skill",
                    "instructions": "Test instructions",
                    "metadata": {"version": "1.0.0"},
                    "tags": ["test"],
                    "resources": {
                        "script.py": b"print('hello')"
                    }
                }
            }
        def search_skills(self, query):
            if query == "error":
                raise ConnectionError("Unreachable")
            return [
                {
                    "name": skill["name"],
                    "description": skill["description"],
                    "tags": skill["tags"]
                }
                for skill in self.skills.values() if query in skill["name"]
            ]
        
        def get_skill(self, name):
            if name == "public/error":
                raise ConnectionError("Unreachable")
            if name == "public/auth":
                from open_skill_registry.client.exceptions import (
                    AuthenticationError as ClientAuthError,
                )
                raise ClientAuthError("Unauthorized")
            if name not in self.skills:
                from open_skill_registry.client.exceptions import (
                    SkillNotFoundError as ClientNotFoundError,
                )
                raise ClientNotFoundError(name)
            return self.skills[name]
            
        def get_skill_resource(self, name, resource_path, version=None):
            if name not in self.skills:
                from open_skill_registry.client.exceptions import (
                    SkillNotFoundError as ClientNotFoundError,
                )
                raise ClientNotFoundError(name)
            res = self.skills[name].get("resources", {})
            if resource_path not in res:
                from open_skill_registry.client.exceptions import (
                    NotFoundError as ClientNotFoundError2,
                )
                raise ClientNotFoundError2(resource_path)
            return res[resource_path]
    return MockSyncRegistry()


@pytest.fixture
def mock_async_client():
    class MockAsyncClient:
        def __init__(self):
            self.skills = {
                "public/test-skill": {
                    "name": "public/test-skill",
                    "description": "A test skill",
                    "instructions": "Test instructions",
                    "metadata": {"version": "1.0.0"},
                    "tags": ["test"],
                    "resources": {
                        "script.py": b"print('hello')"
                    }
                }
            }
        async def search_skills(self, query):
            if query == "error":
                raise ConnectionError("Unreachable")
            return [
                {
                    "name": skill["name"],
                    "description": skill["description"],
                    "tags": skill["tags"]
                }
                for skill in self.skills.values() if query in skill["name"]
            ]
        
        async def get_skill(self, name):
            if name == "public/error":
                raise ConnectionError("Unreachable")
            if name == "public/auth":
                from open_skill_registry.client.exceptions import (
                    AuthenticationError as ClientAuthError,
                )
                raise ClientAuthError("Unauthorized")
            if name not in self.skills:
                from open_skill_registry.client.exceptions import (
                    SkillNotFoundError as ClientNotFoundError,
                )
                raise ClientNotFoundError(name)
            return self.skills[name]
            
        async def get_skill_resource(self, name, resource_path, version=None):
            if name not in self.skills:
                from open_skill_registry.client.exceptions import (
                    SkillNotFoundError as ClientNotFoundError,
                )
                raise ClientNotFoundError(name)
            res = self.skills[name].get("resources", {})
            if resource_path not in res:
                from open_skill_registry.client.exceptions import (
                    NotFoundError as ClientNotFoundError2,
                )
                raise ClientNotFoundError2(resource_path)
            return res[resource_path]
    return MockAsyncClient()


def test_init_validation():
    with pytest.raises(ValueError):
        OpenSkillRegistry()


def test_search_skills_embedded(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    results = registry.search_skills("test")
    assert len(results) == 1
    assert isinstance(results[0], Frontmatter)
    assert results[0].name == "public/test-skill"

def test_search_skills_unreachable_embedded(mock_sync_registry, caplog):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    results = registry.search_skills("error")
    assert len(results) == 0
    assert "error" in caplog.text.lower() or "unreachable" in caplog.text.lower()

def test_get_skill_embedded(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    skill = registry.get_skill("test-skill")
    assert isinstance(skill, Skill)
    assert skill.name == "public/test-skill"
    assert skill.description == "A test skill"

def test_get_skill_not_found(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    with pytest.raises(SkillNotFoundError):
        registry.get_skill("missing")

def test_get_skill_unreachable(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    with pytest.raises(ConnectionError):
        registry.get_skill("error")

def test_get_skill_auth_error(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    with pytest.raises(AuthenticationError):
        registry.get_skill("auth")

def test_get_skill_invalid_name(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    with pytest.raises(ValueError):
        registry.get_skill("inv@lid")
    with pytest.raises(ValueError):
        registry.get_skill("")

def test_get_skill_resource_embedded(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    res = registry.get_skill_resource("test-skill", "script.py")
    assert res == b"print('hello')"

def test_get_skill_resource_not_found(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    with pytest.raises(SkillNotFoundError):
        registry.get_skill_resource("missing", "script.py")
    
    with pytest.raises((SkillNotFoundError, KeyError, RuntimeError)):
        # Could be SkillNotFoundError or NotFoundError
        registry.get_skill_resource("test-skill", "missing.py")


def test_hosted_mode_search(mock_async_client):
    registry = OpenSkillRegistry(client=mock_async_client)
    results = registry.search_skills("test")
    assert len(results) == 1
    assert results[0].name == "public/test-skill"

def test_hosted_mode_get_skill(mock_async_client):
    registry = OpenSkillRegistry(client=mock_async_client)
    skill = registry.get_skill("test-skill")
    assert skill.name == "public/test-skill"
    assert skill.instructions == "Test instructions"

def test_hosted_mode_get_resource(mock_async_client):
    registry = OpenSkillRegistry(client=mock_async_client)
    res = registry.get_skill_resource("test-skill", "script.py")
    assert res == b"print('hello')"

import httpx


def test_hosted_mock_transport_search():
    def handle_request(request):
        if "error" in str(request.url):
            raise httpx.ConnectError("Unreachable")
        return httpx.Response(200, json=[{"name": "public/test", "description": "a", "tags": []}])
    
    transport = httpx.MockTransport(handle_request)
    # create our own client with transport
    from open_skill_registry.client.main import SkillRegistryClient
    client = SkillRegistryClient(base_url="http://testserver", timeout=1.0)
    # Patch the httpx client
    client._client = httpx.Client(transport=transport, base_url="http://testserver")
    
    registry = OpenSkillRegistry(registry=client)
    res = registry.search_skills("test")
    assert len(res) == 1
    assert res[0].name == "public/test"

def test_hosted_mock_transport_search_unreachable():
    def handle_request(request):
        raise httpx.ConnectError("Unreachable")
    
    transport = httpx.MockTransport(handle_request)
    from open_skill_registry.client.main import SkillRegistryClient
    client = SkillRegistryClient(base_url="http://testserver", timeout=1.0)
    client._client = httpx.Client(transport=transport, base_url="http://testserver")
    
    registry = OpenSkillRegistry(registry=client)
    res = registry.search_skills("error")
    assert len(res) == 0

def test_hosted_mock_transport_get_skill():
    def handle_request(request):
        if "error" in str(request.url):
            raise httpx.ConnectError("Unreachable")
        if "missing" in str(request.url):
            return httpx.Response(404, json={"detail": "Not found"})
        if "auth" in str(request.url):
            return httpx.Response(401, json={"detail": "Unauthorized"})
        return httpx.Response(200, json={"name": "public/test", "description": "a", "instructions": "test instructions"})
    
    transport = httpx.MockTransport(handle_request)
    from open_skill_registry.client.main import SkillRegistryClient
    client = SkillRegistryClient(base_url="http://testserver", timeout=1.0)
    client._client = httpx.Client(transport=transport, base_url="http://testserver")
    
    registry = OpenSkillRegistry(registry=client)
    
    # success
    skill = registry.get_skill("test")
    assert skill.name == "public/test"
    
    # 404
    with pytest.raises(SkillNotFoundError):
        registry.get_skill("missing")
        
    # 401
    with pytest.raises(AuthenticationError):
        registry.get_skill("auth")
        
    # unreachable
    with pytest.raises(ConnectionError):
        registry.get_skill("error")

def test_invalid_name_formats(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    with pytest.raises(ValueError):
        registry.get_skill("/bad")
    with pytest.raises(ValueError):
        registry.get_skill("bad/")
    with pytest.raises(ValueError):
        registry.get_skill("")
    with pytest.raises(ValueError):
        registry.get_skill("///")

@pytest.mark.asyncio
async def test_skill_get_resource_async(mock_sync_registry):
    registry = OpenSkillRegistry(registry=mock_sync_registry)
    skill = registry.get_skill("test-skill")
    # Actually call get_resource asynchronously
    res = await skill.get_resource("script.py")
    assert res == b"print('hello')"
