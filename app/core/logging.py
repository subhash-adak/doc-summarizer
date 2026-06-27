import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger


def _add_app_context(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Inject app-level fields into every log entry."""
    event_dict.setdefault("app", "doc-summarizer")
    return event_dict


def setup_logging(log_level: str = "INFO", is_production: bool = False) -> None:
    """
    Configure structlog for the application.
    Call once at startup from main.py.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_app_context,
        structlog.processors.StackInfoRenderer(),
    ]

    if is_production:
        # JSON output 
        renderer = structlog.processors.JSONRenderer()
    else: 
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Silence noisy third-party loggers
    for noisy in ("google.auth", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structured logger. Use this instead of logging.getLogger()."""
    return structlog.get_logger(name)
