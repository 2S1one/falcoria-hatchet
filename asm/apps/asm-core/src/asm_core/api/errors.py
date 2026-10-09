"""HTTP errors raised by the API's access check."""

from fastapi import HTTPException, status


class DetailedHTTPException(HTTPException):
    """Base for the API's HTTP errors; subclasses set `STATUS_CODE` and `DETAIL`."""

    STATUS_CODE = status.HTTP_500_INTERNAL_SERVER_ERROR
    DETAIL = "Server error."

    def __init__(self, detail: str | None = None, headers: dict[str, str] | None = None) -> None:
        super().__init__(
            status_code=self.STATUS_CODE, detail=detail or self.DETAIL, headers=headers
        )


class Unauthorized(DetailedHTTPException):
    """Raised when authentication is missing or invalid."""

    STATUS_CODE = status.HTTP_401_UNAUTHORIZED
    DETAIL = "Not authenticated."


class PermissionDenied(DetailedHTTPException):
    """Raised when the caller is authenticated but not allowed to act."""

    STATUS_CODE = status.HTTP_403_FORBIDDEN
    DETAIL = "Permission denied."


class NotFound(DetailedHTTPException):
    """Raised when the requested project does not exist."""

    STATUS_CODE = status.HTTP_404_NOT_FOUND
    DETAIL = "Not found."


class ServiceUnavailable(DetailedHTTPException):
    """Raised when scanledger is unreachable or answers with an unexpected status."""

    STATUS_CODE = status.HTTP_503_SERVICE_UNAVAILABLE
    DETAIL = "Service unavailable."
