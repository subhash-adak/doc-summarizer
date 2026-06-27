from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class SupportedMimeType(str, Enum):
    PDF = "application/pdf"
    DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    TXT = "text/plain"
    MD = "text/markdown"
    CSV = "text/csv"



class DriveFile(BaseModel):
    """Represents a file entry from Google Drive."""

    id: str = Field(..., description="Google Drive file ID")
    name: str = Field(..., description="File name including extension")
    mime_type: SupportedMimeType = Field(..., description="MIME type of the file")
    size_bytes: Optional[int] = Field(None, description="File size in bytes")
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    web_view_link: Optional[str] = Field(None, description="Direct Drive view URL")

    @property
    def size_kb(self) -> float | None:
        return round(self.size_bytes / 1024, 2) if self.size_bytes else None

    @property
    def extension(self) -> str:
        return self.name.rsplit(".", 1)[-1].lower() if "." in self.name else ""


class ParsedDocument(BaseModel):
    """Document with extracted text content."""

    file: DriveFile
    raw_text: str = Field(..., description="Extracted plain text")
    page_count: Optional[int] = None
    char_count: int = Field(default=0)
    extraction_errors: list[str] = Field(default_factory=list)

    def model_post_init(self, __context: object) -> None:
        self.char_count = len(self.raw_text)
