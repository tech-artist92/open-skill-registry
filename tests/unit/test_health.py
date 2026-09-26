import pytest
from httpx import AsyncClient, ASGITransport
from open_skill_registry.server.app import create_app

@pytest.fixture
def app():
    return create_app()

@pytest.mark.asyncio
async def test_health_check_success(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        
        # Check standard envelope format
        data = response.json()
        assert data["code"] == 0
        assert data["error"] is None
        
        payload = data["data"]
        assert payload["status"] == "ok"
        assert payload["db"] in ("connected", "disconnected", "error")
        assert payload["redis"] in ("connected", "in-memory", "disabled", "error")
        assert "embeddings" in payload

@pytest.mark.asyncio
async def test_api_v1_health_check_success(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["code"] == 0

@pytest.mark.asyncio
async def test_request_id_header(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert "x-request-id" in response.headers

@pytest.mark.asyncio
async def test_404_error_handler(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/non-existent-route")
        assert response.status_code == 404
        
        data = response.json()
        assert data["code"] == 404
        assert "Not Found" in data["error"]
        assert data.get("data") is None

@pytest.mark.asyncio
async def test_422_error_handler(app):
    @app.get("/test-422")
    async def dummy_route(param: int):
        return {"param": param}
        
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test-422?param=not-an-int")
        assert response.status_code == 422
        
        data = response.json()
        assert data["code"] == 422
        assert data["error"] == "Validation error"
        assert "errors" in data["data"]
