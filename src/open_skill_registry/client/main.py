import io
from pathlib import Path
from typing import Optional, Any, Union, Dict
import httpx

from open_skill_registry.client.exceptions import (
    NotFoundError,
    SkillNotFoundError,
    AuthenticationError,
    DuplicateVersionError,
    OpenSkillRegistryClientError
)

def _handle_response(response: httpx.Response, expect_json: bool = True) -> Any:
    if response.status_code >= 400:
        if response.status_code == 404:
            raise NotFoundError(f"Resource not found: {response.text}")
        elif response.status_code in (401, 403):
            raise AuthenticationError(f"Authentication failed: {response.text}")
        elif response.status_code == 409:
            raise DuplicateVersionError(f"Duplicate version: {response.text}")
        elif response.status_code == 400:
            raise ValueError(f"Bad request: {response.text}")
        else:
            raise OpenSkillRegistryClientError(f"HTTP error {response.status_code}: {response.text}")
    
    if expect_json:
        try:
            data = response.json()
            return data.get("data", data)
        except ValueError:
            return response.text
    return response.content

class AsyncSkillRegistryClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        transport: Optional[httpx.BaseTransport] = None
    ):
        self.base_url = base_url.rstrip("/")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            transport=transport
        )

    async def __aenter__(self):
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def aclose(self):
        await self._client.aclose()

    async def search(self, query: str, limit: int = 10, namespace: Optional[str] = None) -> Any:
        params = {"query": query, "limit": limit}
        if namespace:
            params["namespace"] = namespace
        response = await self._client.get("/api/v1/skills/search", params=params)
        return _handle_response(response)

    async def list_skills(self, page: int = 1, size: int = 20, namespace: Optional[str] = None, sort: str = "updated") -> Any:
        params = {"page": page, "size": size, "sort": sort}
        if namespace:
            params["namespace"] = namespace
        response = await self._client.get("/api/v1/skills", params=params)
        return _handle_response(response)

    async def get_skill(self, namespace: str, slug: str) -> Any:
        response = await self._client.get(f"/api/v1/skills/{namespace}/{slug}")
        return _handle_response(response)

    async def get_version(self, namespace: str, slug: str, version: str) -> Any:
        response = await self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}")
        return _handle_response(response)

    async def get_instructions(self, namespace: str, slug: str, version: str) -> str:
        response = await self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}/instructions")
        return _handle_response(response)

    async def get_file(self, namespace: str, slug: str, version: str, path: str) -> bytes:
        response = await self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}/files/{path}")
        return _handle_response(response, expect_json=False)

    async def publish(
        self,
        file_data: Union[bytes, io.BytesIO, str, Path],
        namespace: str = "public",
        slug: Optional[str] = None,
        version: Optional[str] = None
    ) -> Any:
        if isinstance(file_data, str):
            if Path(file_data).exists():
                file_data = Path(file_data).read_bytes()
            else:
                file_data = file_data.encode()
        elif isinstance(file_data, Path):
            file_data = file_data.read_bytes()
        elif isinstance(file_data, io.BytesIO):
            file_data = file_data.getvalue()

        data = {"namespace": namespace}
        if slug:
            data["slug"] = slug
        if version:
            data["version"] = version

        files = {"file": ("package.tar.gz", file_data, "application/gzip")}
        
        response = await self._client.post("/api/v1/skills/publish", data=data, files=files)
        return _handle_response(response)

class SkillRegistryClient:
    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        transport: Optional[httpx.BaseTransport] = None
    ):
        self.base_url = base_url.rstrip("/")
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            transport=transport
        )

    def __enter__(self):
        self._client.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._client.__exit__(exc_type, exc_val, exc_tb)

    def close(self):
        self._client.close()

    def search(self, query: str, limit: int = 10, namespace: Optional[str] = None) -> Any:
        params = {"query": query, "limit": limit}
        if namespace:
            params["namespace"] = namespace
        response = self._client.get("/api/v1/skills/search", params=params)
        return _handle_response(response)

    def list_skills(self, page: int = 1, size: int = 20, namespace: Optional[str] = None, sort: str = "updated") -> Any:
        params = {"page": page, "size": size, "sort": sort}
        if namespace:
            params["namespace"] = namespace
        response = self._client.get("/api/v1/skills", params=params)
        return _handle_response(response)

    def get_skill(self, namespace: str, slug: str) -> Any:
        response = self._client.get(f"/api/v1/skills/{namespace}/{slug}")
        return _handle_response(response)

    def get_version(self, namespace: str, slug: str, version: str) -> Any:
        response = self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}")
        return _handle_response(response)

    def get_instructions(self, namespace: str, slug: str, version: str) -> str:
        response = self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}/instructions")
        return _handle_response(response)

    def get_file(self, namespace: str, slug: str, version: str, path: str) -> bytes:
        response = self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}/files/{path}")
        return _handle_response(response, expect_json=False)

    def publish(
        self,
        file_data: Union[bytes, io.BytesIO, str, Path],
        namespace: str = "public",
        slug: Optional[str] = None,
        version: Optional[str] = None
    ) -> Any:
        if isinstance(file_data, str):
            if Path(file_data).exists():
                file_data = Path(file_data).read_bytes()
            else:
                file_data = file_data.encode()
        elif isinstance(file_data, Path):
            file_data = file_data.read_bytes()
        elif isinstance(file_data, io.BytesIO):
            file_data = file_data.getvalue()

        data = {"namespace": namespace}
        if slug:
            data["slug"] = slug
        if version:
            data["version"] = version

        files = {"file": ("package.tar.gz", file_data, "application/gzip")}
        
        response = self._client.post("/api/v1/skills/publish", data=data, files=files)
        return _handle_response(response)
