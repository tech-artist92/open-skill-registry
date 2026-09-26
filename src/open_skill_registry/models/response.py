"""Shared API response envelope and pagination models (T007)."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

T = TypeVar("T")


class ResponseEnvelope(BaseModel, Generic[T]):
    """Standard unified response envelope for API responses."""

    model_config = ConfigDict(frozen=True)

    data: T | None = None
    error: str | None = None
    code: int = 200
    meta: dict[str, Any] | None = None
    message: str | None = None


class Page(BaseModel, Generic[T]):
    """Standard pagination wrapper for collections."""

    model_config = ConfigDict(frozen=True)

    items: list[T]
    total: int
    page: int
    page_size: int
    has_more: bool = False

    @model_validator(mode="before")
    @classmethod
    def compute_has_more(cls, data: Any) -> Any:
        if isinstance(data, dict) and (
            "has_more" not in data or data["has_more"] is None
        ):
            page = data.get("page", 1)
            page_size = data.get("page_size", len(data.get("items", [])))
            total = data.get("total", 0)
            data["has_more"] = (page * page_size) < total
        return data
