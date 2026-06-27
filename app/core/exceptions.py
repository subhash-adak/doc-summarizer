from fastapi import HTTPException, status


class DocSummarizerError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or message


# Auth / Drive 

class AuthenticationError(DocSummarizerError):
    """Raised when OAuth2 flow fails or token is invalid."""


class DriveAccessError(DocSummarizerError):
    """Raised when Google Drive API returns an error."""


class FolderNotFoundError(DriveAccessError):
    """Raised when the configured Drive folder does not exist or is inaccessible."""


# Parsing 

class DocumentParseError(DocSummarizerError):
    """Raised when text extraction from a document fails."""


class UnsupportedFileTypeError(DocSummarizerError):
    """Raised when a file type is not supported for parsing."""

    def __init__(self, mime_type: str) -> None:
        super().__init__(
            message=f"Unsupported file type: {mime_type}",
            detail=f"Supported types: application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document, text/plain, text/markdown, text/csv",
        )
        self.mime_type = mime_type


# Summarization 

class SummarizationError(DocSummarizerError):
    """Raised when Vertex AI returns an error or unexpected response."""


class EmptyDocumentError(DocSummarizerError):
    """Raised when a document contains no extractable text."""


# HTTP Exception Factories 

def http_401(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def http_403(detail: str = "Access denied") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def http_404(detail: str = "Not found") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def http_422(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def http_500(detail: str = "Internal server error") -> HTTPException:
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)
