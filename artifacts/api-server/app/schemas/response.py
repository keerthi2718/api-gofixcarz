from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard API response envelope."""

    success: bool
    message: str
    data: Optional[T] = None
    errors: List[Any] = []
    status_code: int

    @classmethod
    def ok(
        cls,
        data: Any = None,
        message: str = "Success",
        status_code: int = 200,
    ) -> "APIResponse":
        return cls(success=True, message=message, data=data, errors=[], status_code=status_code)

    @classmethod
    def created(cls, data: Any = None, message: str = "Created successfully") -> "APIResponse":
        return cls(success=True, message=message, data=data, errors=[], status_code=201)

    @classmethod
    def error(
        cls,
        message: str = "Error",
        status_code: int = 400,
        errors: Optional[List[Any]] = None,
    ) -> "APIResponse":
        return cls(
            success=False, message=message, data=None, errors=errors or [], status_code=status_code
        )


class PaginatedData(BaseModel, Generic[T]):
    """Paginated response data wrapper."""

    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int
