from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DriveFile


class SummaryStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  


class DocumentSummary(BaseModel):
    """The result of summarizing a single document."""
    model_config = ConfigDict(protected_namespaces=())

    file: DriveFile
    status: SummaryStatus = SummaryStatus.COMPLETED
    summary: Optional[str] = Field(None, description="AI-generated summary (5-10 sentences)")
    char_count: int = Field(default=0, description="Character count of source document")
    chunk_count: int = Field(default=1, description="Number of chunks used (1 = direct summary)")
    model_used: str = Field(default="gemini-2.5-flash")
    processing_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    summarized_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_success(self) -> bool:
        return self.status == SummaryStatus.COMPLETED


class SummarizeRequest(BaseModel):
    """Request body for the /api/documents/summarize endpoint."""

    file_ids: list[str] = Field(
        ...,
        min_length=1,
        description="List of Google Drive file IDs to summarize",
    )


class SummarizeResponse(BaseModel):
    """Response from the summarize endpoint."""

    total: int
    succeeded: int
    failed: int
    results: list[DocumentSummary]
    started_at: datetime
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def duration_seconds(self) -> float:
        return (self.completed_at - self.started_at).total_seconds()
