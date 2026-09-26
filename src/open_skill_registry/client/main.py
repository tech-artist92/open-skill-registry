import io
import os
from pathlib import Path
from typing import Optional, Any, Union, Dict

import httpx

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

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
            if isinstance(data, dict):
                return data.get("data", data)
            return data
        except ValueError:
            return response.text
    return response.content

class AsyncSkillRegistryClient:
    """
    An asynchronous client for the Open Skill Registry API.
    """
    def __init__(
        self,
        base_url: Optional[str] = "http://localhost:8080",
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        transport: Optional[httpx.AsyncBaseTransport] = None
    ):
        base_url = base_url or "http://localhost:8080"
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

    async def __aenter__(self) -> Self:
        await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def search(self, query: str, limit: int = 10, namespace: Optional[str] = None) -> Any:
        """
        Search for skills.
        
        Args:
            query: The search query string.
            limit: Maximum number of results to return.
            namespace: Optional namespace to filter the search.
            
        Returns:
            A dictionary containing search results.
        """
        params = {"query": query, "limit": limit}
        if namespace:
            params["namespace"] = namespace
        response = await self._client.get("/api/v1/skills/search", params=params)
        return _handle_response(response)

    async def list_skills(self, page: int = 1, size: int = 20, namespace: Optional[str] = None, sort: str = "updated") -> Any:
        """
        List all skills, optionally filtered by namespace.
        
        Args:
            page: Page number for pagination.
            size: Number of items per page.
            namespace: Optional namespace filter.
            sort: Sorting criteria.
            
        Returns:
            A list of skills or pagination metadata.
        """
        params = {"page": page, "size": size, "sort": sort}
        if namespace:
            params["namespace"] = namespace
        response = await self._client.get("/api/v1/skills", params=params)
        return _handle_response(response)

    async def get_skill(self, namespace: str, slug: str) -> Any:
        """
        Get metadata for a specific skill.
        
        Args:
            namespace: The namespace of the skill.
            slug: The slug of the skill.
            
        Returns:
            Skill metadata.
        """
        response = await self._client.get(f"/api/v1/skills/{namespace}/{slug}")
        return _handle_response(response)

    async def get_version(self, namespace: str, slug: str, version: str) -> Any:
        """
        Get metadata for a specific version of a skill.
        
        Args:
            namespace: The namespace of the skill.
            slug: The slug of the skill.
            version: The version string.
            
        Returns:
            Version metadata.
        """
        response = await self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}")
        return _handle_response(response)

    async def get_instructions(self, namespace: str, slug: str, version: str) -> str:
        """
        Get instructions for a specific version of a skill.
        
        Args:
            namespace: The namespace of the skill.
            slug: The slug of the skill.
            version: The version string.
            
        Returns:
            Instructions as a string.
        """
        response = await self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}/instructions")
        return _handle_response(response)

    async def get_file(self, namespace: str, slug: str, version: str, path: str) -> bytes:
        """
        Get a specific file from a skill version package.
        
        Args:
            namespace: The namespace of the skill.
            slug: The slug of the skill.
            version: The version string.
            path: The relative file path inside the skill package.
            
        Returns:
            File content as bytes.
        """
        response = await self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}/files/{path}")
        return _handle_response(response, expect_json=False)

    async def publish(
        self,
        file_data: Union[bytes, io.BytesIO, str, Path],
        namespace: str = "public",
        slug: Optional[str] = None,
        version: Optional[str] = None
    ) -> Any:
        """
        Publish a new skill or a new version of an existing skill.
        
        Args:
            file_data: The skill package file content or path.
            namespace: The namespace to publish to.
            slug: The slug of the skill (optional).
            version: The version string (optional).
            
        Returns:
            Publication result metadata.
        """
        if isinstance(file_data, str):
            is_path = False
            if "\n" not in file_data and len(file_data) < 4096:
                try:
                    if Path(file_data).exists():
                        is_path = True
                except OSError:
                    pass
            if is_path:
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

    async def create_namespace(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
        visibility: str = "PUBLIC"
    ) -> Any:
        body = {"slug": slug, "name": name, "description": description, "visibility": visibility}
        response = await self._client.post("/api/v1/namespaces", json=body)
        return _handle_response(response)

    async def list_namespaces(self, page: int = 1, size: int = 20) -> Any:
        params = {"page": page, "size": size}
        response = await self._client.get("/api/v1/namespaces", params=params)
        return _handle_response(response)

    async def get_namespace(self, slug: str) -> Any:
        response = await self._client.get(f"/api/v1/namespaces/{slug}")
        return _handle_response(response)

    async def update_namespace(
        self,
        slug: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        visibility: Optional[str] = None
    ) -> Any:
        body = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if visibility is not None:
            body["visibility"] = visibility
        response = await self._client.put(f"/api/v1/namespaces/{slug}", json=body)
        return _handle_response(response)

    async def create_key(
        self,
        label: str,
        namespace_slug: Optional[str] = None,
        permissions: Optional[list[str]] = None,
        expires_at: Optional[Any] = None
    ) -> Any:
        body = {"label": label, "namespace_slug": namespace_slug, "permissions": permissions or ["READ", "WRITE"]}
        if expires_at is not None:
            body["expires_at"] = expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at)
        response = await self._client.post("/api/v1/keys", json=body)
        return _handle_response(response)

    async def list_keys(self, namespace: Optional[str] = None) -> Any:
        params = {}
        if namespace:
            params["namespace"] = namespace
        response = await self._client.get("/api/v1/keys", params=params)
        return _handle_response(response)

    async def revoke_key(self, key_id: str) -> Any:
        response = await self._client.delete(f"/api/v1/keys/{key_id}")
        return _handle_response(response)

class SkillRegistryClient:
    """
    A synchronous client for the Open Skill Registry API.
    """
    def __init__(
        self,
        base_url: Optional[str] = "http://localhost:8080",
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        transport: Optional[httpx.BaseTransport] = None
    ):
        base_url = base_url or "http://localhost:8080"
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

    def __enter__(self) -> Self:
        self._client.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._client.__exit__(exc_type, exc_val, exc_tb)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def search(self, query: str, limit: int = 10, namespace: Optional[str] = None) -> Any:
        """
        Search for skills.
        
        Args:
            query: The search query string.
            limit: Maximum number of results to return.
            namespace: Optional namespace to filter the search.
            
        Returns:
            A dictionary containing search results.
        """
        params = {"query": query, "limit": limit}
        if namespace:
            params["namespace"] = namespace
        response = self._client.get("/api/v1/skills/search", params=params)
        return _handle_response(response)

    def list_skills(self, page: int = 1, size: int = 20, namespace: Optional[str] = None, sort: str = "updated") -> Any:
        """
        List all skills, optionally filtered by namespace.
        
        Args:
            page: Page number for pagination.
            size: Number of items per page.
            namespace: Optional namespace filter.
            sort: Sorting criteria.
            
        Returns:
            A list of skills or pagination metadata.
        """
        params = {"page": page, "size": size, "sort": sort}
        if namespace:
            params["namespace"] = namespace
        response = self._client.get("/api/v1/skills", params=params)
        return _handle_response(response)

    def get_skill(self, namespace: str, slug: str) -> Any:
        """
        Get metadata for a specific skill.
        
        Args:
            namespace: The namespace of the skill.
            slug: The slug of the skill.
            
        Returns:
            Skill metadata.
        """
        response = self._client.get(f"/api/v1/skills/{namespace}/{slug}")
        return _handle_response(response)

    def get_version(self, namespace: str, slug: str, version: str) -> Any:
        """
        Get metadata for a specific version of a skill.
        
        Args:
            namespace: The namespace of the skill.
            slug: The slug of the skill.
            version: The version string.
            
        Returns:
            Version metadata.
        """
        response = self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}")
        return _handle_response(response)

    def get_instructions(self, namespace: str, slug: str, version: str) -> str:
        """
        Get instructions for a specific version of a skill.
        
        Args:
            namespace: The namespace of the skill.
            slug: The slug of the skill.
            version: The version string.
            
        Returns:
            Instructions as a string.
        """
        response = self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}/instructions")
        return _handle_response(response)

    def get_file(self, namespace: str, slug: str, version: str, path: str) -> bytes:
        """
        Get a specific file from a skill version package.
        
        Args:
            namespace: The namespace of the skill.
            slug: The slug of the skill.
            version: The version string.
            path: The relative file path inside the skill package.
            
        Returns:
            File content as bytes.
        """
        response = self._client.get(f"/api/v1/skills/{namespace}/{slug}/versions/{version}/files/{path}")
        return _handle_response(response, expect_json=False)

    def publish(
        self,
        file_data: Union[bytes, io.BytesIO, str, Path],
        namespace: str = "public",
        slug: Optional[str] = None,
        version: Optional[str] = None
    ) -> Any:
        """
        Publish a new skill or a new version of an existing skill.
        
        Args:
            file_data: The skill package file content or path.
            namespace: The namespace to publish to.
            slug: The slug of the skill (optional).
            version: The version string (optional).
            
        Returns:
            Publication result metadata.
        """
        if isinstance(file_data, str):
            is_path = False
            if "\n" not in file_data and len(file_data) < 4096:
                try:
                    if Path(file_data).exists():
                        is_path = True
                except OSError:
                    pass
            if is_path:
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

    def create_namespace(
        self,
        slug: str,
        name: str,
        description: Optional[str] = None,
        visibility: str = "PUBLIC"
    ) -> Any:
        body = {"slug": slug, "name": name, "description": description, "visibility": visibility}
        response = self._client.post("/api/v1/namespaces", json=body)
        return _handle_response(response)

    def list_namespaces(self, page: int = 1, size: int = 20) -> Any:
        params = {"page": page, "size": size}
        response = self._client.get("/api/v1/namespaces", params=params)
        return _handle_response(response)

    def get_namespace(self, slug: str) -> Any:
        response = self._client.get(f"/api/v1/namespaces/{slug}")
        return _handle_response(response)

    def update_namespace(
        self,
        slug: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        visibility: Optional[str] = None
    ) -> Any:
        body = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if visibility is not None:
            body["visibility"] = visibility
        response = self._client.put(f"/api/v1/namespaces/{slug}", json=body)
        return _handle_response(response)

    def create_key(
        self,
        label: str,
        namespace_slug: Optional[str] = None,
        permissions: Optional[list[str]] = None,
        expires_at: Optional[Any] = None
    ) -> Any:
        body = {"label": label, "namespace_slug": namespace_slug, "permissions": permissions or ["READ", "WRITE"]}
        if expires_at is not None:
            body["expires_at"] = expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at)
        response = self._client.post("/api/v1/keys", json=body)
        return _handle_response(response)

    def list_keys(self, namespace: Optional[str] = None) -> Any:
        params = {}
        if namespace:
            params["namespace"] = namespace
        response = self._client.get("/api/v1/keys", params=params)
        return _handle_response(response)

    def revoke_key(self, key_id: str) -> Any:
        response = self._client.delete(f"/api/v1/keys/{key_id}")
        return _handle_response(response)

