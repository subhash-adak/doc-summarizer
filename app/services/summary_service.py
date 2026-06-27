import asyncio
import time
from typing import Optional

import vertexai
from google.oauth2 import service_account
from vertexai.generative_models import GenerationConfig, GenerativeModel

from app.core.config import get_settings
from app.core.exceptions import SummarizationError
from app.core.logging import get_logger
from app.models.document import ParsedDocument
from app.models.summary import DocumentSummary, SummaryStatus
from app.utils.chunker import split_text

logger = get_logger(__name__)

# Prompts 
_DIRECT_SUMMARY_PROMPT = """\
You are an expert document analyst. Summarise the following document in 5 to 10 clear, \
informative sentences. Cover the main topic, key findings or arguments, and any \
important conclusions or recommendations. Write in plain English suitable for a \
professional audience. Do not include phrases like "This document..." or "The text states...".

DOCUMENT:
{text}

SUMMARY:"""

_CHUNK_SUMMARY_PROMPT = """\
Summarise the following section of a larger document in 3 to 5 sentences, \
capturing the key information in this section only.

SECTION:
{text}

SECTION SUMMARY:"""

_SYNTHESIS_PROMPT = """\
You are given a series of section summaries from a single large document. \
Synthesise them into one cohesive summary of 5 to 10 sentences that captures \
the overall topic, key findings, and conclusions of the full document.

SECTION SUMMARIES:
{summaries}

FINAL SUMMARY:"""


class SummaryService:
    """
    Manages all summarization logic against Vertex AI Gemini.

    Initialise once at app startup and inject where needed.
    """

    def __init__(self) -> None:
        settings = get_settings()

        if settings.demo_mode:
            self._model = None
            self._generation_config = None
            logger.info("summary_service_initialised_demo_mode")
            return

        # Build credentials
        # ADC works automatically on Cloud Run / GKE; SA JSON is required for local dev.
        credentials = None
        if settings.vertex_sa_path and settings.vertex_sa_path.exists():
            credentials = service_account.Credentials.from_service_account_file(
                str(settings.vertex_sa_path),
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            logger.info("vertex_auth_service_account", path=str(settings.vertex_sa_path))
        else:
            logger.info("vertex_auth_adc")  # Application Default Credentials

        vertexai.init(
            project=settings.gcp_project_id,
            location=settings.gcp_location,
            credentials=credentials,   # None → ADC is used automatically
        )
        self._model = GenerativeModel(settings.vertex_model)
        self._generation_config = GenerationConfig(
            temperature=settings.summary_temperature,
            max_output_tokens=settings.summary_max_tokens,
            candidate_count=1,
        )
        logger.info(
            "summary_service_initialised",
            model=settings.vertex_model,
            project=settings.gcp_project_id,
            location=settings.gcp_location,
        )

    async def summarise(self, parsed_doc: ParsedDocument) -> DocumentSummary:
        """
        Produce a DocumentSummary for a ParsedDocument.
        Automatically selects direct vs map-reduce strategy.
        """
        settings = get_settings()
        started = time.monotonic()
        text = parsed_doc.raw_text.strip()

        # Guard: empty document 
        if not text:
            logger.warning("empty_document", file_id=parsed_doc.file.id)
            return DocumentSummary(
                file=parsed_doc.file,
                status=SummaryStatus.SKIPPED,
                error_message="Document contains no extractable text.",
                char_count=0,
                model_used=settings.vertex_model if not settings.demo_mode else "gemini-2.5-flash (Mock Mode)",
            )

        if settings.demo_mode:
            # Simulate slight processing latency for realistic feedback
            await asyncio.sleep(1.0)
            mock_summaries = {
                "mock-file-1": "The Q3 Financial Report shows a solid 14% year-over-year revenue growth, reaching $42.5 million. Operative margins expanded to 18.2% due to successful cost optimization in corporate services. Strong growth was observed in cloud services, offsetting minor declines in legacy enterprise licenses. Cash reserves grew to $15 million, positioning the company well for proposed Q4 strategic acquisitions. The report outlines minor risks regarding supply chain bottlenecks in key manufacturing segments.",
                "mock-file-2": "This marketing strategy document outlines the roadmap for launching the Product X update in late Q3. Key channels include organic social campaigns, targeted email marketing, and premium sponsorships at industry events. A dedicated influencer outreach program will target 50 top-tier tech content creators. The total marketing budget is allocated at $250,000, with 40% reserved for paid performance ads. Key performance indicators (KPIs) include a target of 50,000 new signups and an conversion rate of 3.5%.",
                "mock-file-3": "This guide details the step-by-step setup of the corporate staging servers. It includes guidelines on configuring SSH access, setting up docker containers, and enforcing TLS 1.3 encryption. Key server credentials are listed in environment configurations, with instructions on using secret vaults. The document specifies that automatic backups must run daily at 02:00 UTC and be stored in multi-region cloud buckets. System administrators are instructed to monitor log trails using structured logging endpoints.",
                "mock-file-5": "The product roadmap details the milestones for the DocSummarizer application across three distinct phases. Phase 1 centers on establishing core features, including Google Drive integration via OAuth2 and basic document parsing. Phase 2 introduces Server-Sent Events (SSE) to support live summarization progress streaming. Phase 3 focuses on export capabilities, expanding document types, and finalizing security hardening. Estimated timelines span 6 weeks total for development and deployment.",
                "mock-file-6": "The customer feedback dataset contains ratings and comments regarding the document summarization tool. Analysis reveals an average customer satisfaction score of 4.7 out of 5 stars. Users heavily praised the platform's speed, interface design, and dynamic progress bar. Some users requested support for additional file formats like Markdown and CSV files. Overall, the feedback demonstrates strong product-market fit and high user engagement.",
            }
            summary_text = mock_summaries.get(
                parsed_doc.file.id,
                f"This is a high-quality mock summary for the document '{parsed_doc.file.name}' containing {len(text)} characters of text. The content indicates standard configuration guidelines, operational parameters, and executive summaries typical of corporate document assets."
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            return DocumentSummary(
                file=parsed_doc.file,
                status=SummaryStatus.COMPLETED,
                summary=summary_text,
                char_count=len(text),
                chunk_count=1,
                model_used="gemini-2.5-flash (Mock Mode)",
                processing_time_ms=elapsed_ms,
            )

        # Choose strategy 
        chunks = split_text(text)
        chunk_count = len(chunks)

        try:
            if chunk_count == 1:
                summary_text = await self._direct_summary(text)
            else:
                summary_text = await self._map_reduce_summary(chunks)

        except Exception as exc:
            logger.error(
                "summarisation_failed",
                file_id=parsed_doc.file.id,
                error=str(exc),
                exc_info=True,
            )
            return DocumentSummary(
                file=parsed_doc.file,
                status=SummaryStatus.FAILED,
                error_message=str(exc),
                char_count=len(text),
                chunk_count=chunk_count,
                model_used=settings.vertex_model,
                processing_time_ms=int((time.monotonic() - started) * 1000),
            )

        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "summarisation_complete",
            file_id=parsed_doc.file.id,
            file_name=parsed_doc.file.name,
            chunk_count=chunk_count,
            processing_time_ms=elapsed_ms,
        )

        return DocumentSummary(
            file=parsed_doc.file,
            status=SummaryStatus.COMPLETED,
            summary=summary_text,
            char_count=len(text),
            chunk_count=chunk_count,
            model_used=settings.vertex_model,
            processing_time_ms=elapsed_ms,
        )

    # Private: strategy implementations

    async def _direct_summary(self, text: str) -> str:
        """Single API call — used when document fits in Gemini's context."""
        prompt = _DIRECT_SUMMARY_PROMPT.format(text=text)
        return await self._call_gemini(prompt)

    async def _map_reduce_summary(self, chunks: list[str]) -> str:
        """
        Map: summarise each chunk concurrently (bounded concurrency).
        Reduce: synthesise chunk summaries into a final summary.
        """
        logger.info("map_reduce_started", chunk_count=len(chunks))

        # Map phase — process up to 5 chunks concurrently to avoid rate limits
        semaphore = asyncio.Semaphore(5)

        async def summarise_chunk(chunk: str) -> str:
            async with semaphore:
                return await self._call_gemini(
                    _CHUNK_SUMMARY_PROMPT.format(text=chunk)
                )

        chunk_summaries = await asyncio.gather(
            *[summarise_chunk(chunk) for chunk in chunks]
        )

        # Reduce phase
        numbered = "\n\n".join(
            f"[Section {i + 1}]\n{s}" for i, s in enumerate(chunk_summaries)
        )
        return await self._call_gemini(_SYNTHESIS_PROMPT.format(summaries=numbered))

    async def _call_gemini(self, prompt: str) -> str:
        """
        Async wrapper around the blocking Vertex AI SDK call.
        Runs in a thread pool so it doesn't block the event loop.
        Applies exponential backoff retries.
        """
        from app.utils.retry import retry_async

        def _sync_call() -> str:
            response = self._model.generate_content(
                prompt,
                generation_config=self._generation_config,
            )
            if not response.candidates:
                raise SummarizationError("Gemini returned no candidates.")
            
            candidate = response.candidates[0]
            # Safely get safety ratings if available
            ratings = []
            if hasattr(candidate, "safety_ratings"):
                for r in candidate.safety_ratings:
                    ratings.append({"category": str(r.category), "probability": str(r.probability)})
            
            logger.info(
                "gemini_generation_complete",
                finish_reason=str(candidate.finish_reason),
                safety_ratings=ratings,
            )
            return response.text.strip()

        async def _async_call() -> str:
            return await asyncio.to_thread(_sync_call)

        try:
            return await retry_async(
                _async_call,
                max_retries=3,
                initial_delay=2.0,
                backoff_factor=2.0,
                jitter=1.0,
                exceptions_to_retry=(Exception,),
            )
        except Exception as exc:
            raise SummarizationError(f"Vertex AI call failed: {exc}") from exc
