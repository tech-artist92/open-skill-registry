import re

with open("tests/contract/test_retrieval_endpoints.py", "r") as f:
    code = f.read()

tests_to_add = """
@pytest.mark.asyncio
async def test_get_skill_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/skills/ns/nonexistent")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_skill_version_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/9.9.9")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_skill_file_404(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/1.0.0/file?path=nonexistent.py")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_get_skill_file_path_traversal_backslash(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await populate_db(client)
        response = await client.get("/api/v1/skills/ns/slug/versions/1.0.0/file?path=..\\\\test.py")
        assert response.status_code == 400
"""

if "test_get_skill_404" not in code:
    code += tests_to_add
    
with open("tests/contract/test_retrieval_endpoints.py", "w") as f:
    f.write(code)
