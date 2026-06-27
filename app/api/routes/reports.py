from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse

from app.core.exceptions import http_404
from app.core.logging import get_logger
from app.models.summary import DocumentSummary
from app.utils.report_builder import build_csv, build_pdf

router = APIRouter(prefix="/api/reports", tags=["reports"])
logger = get_logger(__name__)

_results_store: dict[str, list[DocumentSummary]] = {}


def store_results(session_id: str, results: list[DocumentSummary]) -> None:
    _results_store[session_id] = results


def get_results(session_id: str) -> list[DocumentSummary]:
    results = _results_store.get(session_id)
    if not results:
        raise http_404("No summarization results found. Run a summarization first.")
    return results


# Routes 

@router.get("/csv", summary="Download results as CSV")
async def download_csv(request: Request) -> StreamingResponse:
    """Stream a UTF-8 CSV report of the latest summarization run."""
    session_id = request.session.get("session_id", "default")
    results = get_results(session_id)

    csv_bytes = build_csv(results)
    filename = f"doc_summaries_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    logger.info("csv_report_downloaded", record_count=len(results))
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pdf", summary="Download results as PDF")
async def download_pdf(request: Request) -> Response:
    """Return a styled PDF report of the latest summarization run."""
    session_id = request.session.get("session_id", "default")
    results = get_results(session_id)

    pdf_bytes = build_pdf(results)
    filename = f"doc_summaries_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"

    logger.info("pdf_report_downloaded", record_count=len(results))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
