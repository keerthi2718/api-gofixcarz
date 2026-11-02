from typing import Any, List, Optional


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        status_code: int = 400,
        errors: Optional[List[Any]] = None,
        error_code: Optional[str] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.errors = errors or []
        self.error_code = error_code
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", errors: Optional[List[Any]] = None):
        super().__init__(message=message, status_code=404, errors=errors)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Unauthorized", errors: Optional[List[Any]] = None):
        super().__init__(message=message, status_code=401, errors=errors)


class ForbiddenException(AppException):
    def __init__(self, message: str = "Forbidden", errors: Optional[List[Any]] = None):
        super().__init__(message=message, status_code=403, errors=errors)


class ConflictException(AppException):
    def __init__(self, message: str = "Conflict", errors: Optional[List[Any]] = None):
        super().__init__(message=message, status_code=409, errors=errors)


class ValidationException(AppException):
    def __init__(self, message: str = "Validation error", errors: Optional[List[Any]] = None):
        super().__init__(message=message, status_code=422, errors=errors)


class BadRequestException(AppException):
    def __init__(self, message: str = "Bad request", errors: Optional[List[Any]] = None):
        super().__init__(message=message, status_code=400, errors=errors)
