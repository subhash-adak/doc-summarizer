from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes import auth, documents, reports
from app.core.config import get_settings
from app.core.exceptions import DocSummarizerError
from app.core.logging import get_logger, setup_logging
from app.services.drive_service import DriveService

# Startup / shutdown lifecycle 

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, is_production=settings.is_production)
    logger = get_logger("main")
    logger.info(
        "app_starting",
        env=settings.app_env,
        model=settings.vertex_model,
        project=settings.gcp_project_id,
    )
    yield
    logger.info("app_shutting_down")


# App factory 

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="DocSummarizer",
        description="AI-powered document summarization via Google Drive + Vertex AI Gemini",
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Middleware 
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        same_site="lax",
        https_only=settings.is_production,
    )

    # Static files & templates 
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")

    # Routes 
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(reports.router)

    # Global exception handlers 

    @app.exception_handler(DocSummarizerError)
    async def domain_exception_handler(
        request: Request, exc: DocSummarizerError
    ) -> JSONResponse:
        logger = get_logger("exception_handler")
        logger.error("domain_error", error=exc.message, detail=exc.detail)
        return JSONResponse(
            status_code=500,
            content={"error": exc.message, "detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger = get_logger("exception_handler")
        logger.error("unhandled_error", error=str(exc), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "An unexpected error occurred."},
        )

    #  UI routes 

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request) -> HTMLResponse:
        credentials = DriveService.load_credentials()
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "authenticated": credentials is not None,
                "app_name": "DocSummarizer",
                "demo_mode": get_settings().demo_mode,
            },
        )

    @app.get("/health", tags=["ops"], summary="Health check")
    async def health() -> dict:
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()




