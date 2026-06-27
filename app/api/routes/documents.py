import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.core.exceptions import http_401, http_500
from app.core.logging import get_logger
from app.models.summary import DocumentSummary, SummarizeRequest, SummarizeResponse, SummaryStatus
from app.services.drive_service import DriveService
from app.services.parser_service import ParserService
from app.services.summary_service import SummaryService

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = get_logger(__name__)


def get_drive_service() -> DriveService:
    credentials = DriveService.load_credentials()
    if not credentials:
        raise http_401("Not authenticated. Please visit /auth/login first.")
    return DriveService(credentials)


def get_parser_service() -> ParserService:
    return ParserService()


def get_summary_service() -> SummaryService:
    return SummaryService()


def _get_or_create_session_id(request: Request) -> str:
    session_id = request.session.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        request.session["session_id"] = session_id
    return session_id


def _build_failed_summary(file, exc: Exception) -> DocumentSummary:
    return DocumentSummary(
        file=file,
        status=SummaryStatus.FAILED,
        error_message=str(exc),
    )


def _sse_event(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


@router.get("/", summary="List documents in the configured Drive folder")
async def list_documents(
    drive: DriveService = Depends(get_drive_service),
) -> dict:
    """
    Return all supported documents (PDF, DOCX, TXT, MD, CSV) from the Drive folder.
    """
    try:
        files = drive.list_folder_files()
    except Exception as exc:
        logger.error("list_documents_error", error=str(exc))
        raise http_500(f"Failed to list documents: {exc}")

    return {
        "count": len(files),
        "files": [f.model_dump(mode="json") for f in files],
    }


@router.post("/summarize", response_model=SummarizeResponse, summary="Summarize selected documents")
async def summarize_documents(
    summarize_req: SummarizeRequest,
    request: Request,
    drive: DriveService = Depends(get_drive_service),
    parser: ParserService = Depends(get_parser_service),
    summarizer: SummaryService = Depends(get_summary_service),
) -> SummarizeResponse:
    """
    Download, parse, and summarize the requested documents.

    Processes documents sequentially to respect Vertex AI rate limits.
    Returns full results including any per-file errors.
    """
    started_at = datetime.now(timezone.utc)
    results = []

    all_files = drive.list_folder_files()
    file_map = {f.id: f for f in all_files}

    for file_id in summarize_req.file_ids:
        file = file_map.get(file_id)
        if not file:
            logger.warning("file_not_found_in_folder", file_id=file_id)
            continue

        logger.info("processing_file", file_id=file_id, file_name=file.name)

        try:
            content = drive.download_file(file.id)
            parsed = parser.parse(file, content)
            summary = await summarizer.summarise(parsed)
        except Exception as exc:
            logger.error("file_processing_error", file_id=file_id, error=str(exc))
            summary = _build_failed_summary(file, exc)

        results.append(summary)

    succeeded = sum(1 for result in results if result.status == SummaryStatus.COMPLETED)
    failed = sum(1 for result in results if result.status == SummaryStatus.FAILED)

    logger.info(
        "batch_complete",
        total=len(results),
        succeeded=succeeded,
        failed=failed,
    )

    session_id = _get_or_create_session_id(request)
    from app.api.routes.reports import store_results

    store_results(session_id, results)

    return SummarizeResponse(
        total=len(results),
        succeeded=succeeded,
        failed=failed,
        results=results,
        started_at=started_at,
    )


@router.post("/stream", summary="Stream summarization progress via SSE")
async def stream_documents(
    summarize_req: SummarizeRequest,
    request: Request,
    drive: DriveService = Depends(get_drive_service),
    parser: ParserService = Depends(get_parser_service),
    summarizer: SummaryService = Depends(get_summary_service),
) -> StreamingResponse:
    """
    Stream progress and per-file summaries using Server-Sent Events.
    """
    session_id = _get_or_create_session_id(request)
    all_files = drive.list_folder_files()
    file_map = {f.id: f for f in all_files}
    total_requested = len(summarize_req.file_ids)

    async def event_stream():
        started_at = datetime.now(timezone.utc)
        results: list[DocumentSummary] = []

        try:
            for current, file_id in enumerate(summarize_req.file_ids, start=1):
                if await request.is_disconnected():
                    logger.info("stream_client_disconnected", session_id=session_id)
                    break

                file = file_map.get(file_id)
                if not file:
                    logger.warning("file_not_found_in_folder", file_id=file_id)
                    yield _sse_event(
                        "error",
                        {
                            "current": current,
                            "total": total_requested,
                            "message": f"File '{file_id}' is no longer available in the Drive folder.",
                        },
                    )
                    continue

                logger.info("processing_file_stream", file_id=file_id, file_name=file.name)

                try:
                    yield _sse_event(
                        "progress",
                        {
                            "current": current,
                            "total": total_requested,
                            "completed": len(results),
                            "stage": "Downloading",
                            "stage_step": 0,
                            "stage_total": 3,
                            "filename": file.name,
                        },
                    )
                    content = drive.download_file(file.id)

                    yield _sse_event(
                        "progress",
                        {
                            "current": current,
                            "total": total_requested,
                            "completed": len(results),
                            "stage": "Parsing",
                            "stage_step": 1,
                            "stage_total": 3,
                            "filename": file.name,
                        },
                    )
                    parsed = parser.parse(file, content)

                    yield _sse_event(
                        "progress",
                        {
                            "current": current,
                            "total": total_requested,
                            "completed": len(results),
                            "stage": "Summarizing",
                            "stage_step": 2,
                            "stage_total": 3,
                            "filename": file.name,
                        },
                    )
                    summary = await summarizer.summarise(parsed)
                except Exception as exc:
                    logger.error("file_processing_error", file_id=file_id, error=str(exc))
                    summary = _build_failed_summary(file, exc)

                results.append(summary)
                yield _sse_event(
                    "summary",
                    {
                        "current": current,
                        "total": total_requested,
                        "completed": len(results),
                        "result": summary.model_dump(mode="json"),
                    },
                )

            succeeded = sum(1 for result in results if result.status == SummaryStatus.COMPLETED)
            failed = sum(1 for result in results if result.status == SummaryStatus.FAILED)

            logger.info(
                "stream_complete",
                total=len(results),
                requested=total_requested,
                succeeded=succeeded,
                failed=failed,
            )

            from app.api.routes.reports import store_results

            store_results(session_id, results)
            yield _sse_event(
                "complete",
                {
                    "completed": True,
                    "total": len(results),
                    "requested_total": total_requested,
                    "succeeded": succeeded,
                    "failed": failed,
                    "results": [result.model_dump(mode="json") for result in results],
                    "started_at": started_at.isoformat(),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "csv": "/api/reports/csv",
                    "pdf": "/api/reports/pdf",
                },
            )
        except Exception as exc:
            logger.error("stream_processing_error", error=str(exc), exc_info=True)
            yield _sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
