"""Paginated result type for DAL query operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class PaginatedResult(Generic[T]):
    """A page of query results with an opaque continuation cursor."""

    items: list[T]
    next_cursor: str | None
    count: int

    def to_dict(self) -> dict:
        """Serialize for JSON API responses."""
        result: dict = {"items": self.items, "count": self.count}
        if self.next_cursor is not None:
            result["next_cursor"] = self.next_cursor
        return result
