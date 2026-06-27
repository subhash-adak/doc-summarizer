import asyncio
import random
from typing import Any, Awaitable, Callable, TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

async def retry_async(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 4,
    initial_delay: float = 2.0,
    backoff_factor: float = 2.0,
    jitter: float = 1.0,
    exceptions_to_retry: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """
    Executes an async function and retries on specified exceptions with exponential backoff and jitter.

    Args:
        func:                The async function to execute.
        max_retries:         Max number of retry attempts.
        initial_delay:       Initial sleep delay in seconds.
        backoff_factor:      Multiplier applied to delay on each failure.
        jitter:              Max random float added to delay.
        exceptions_to_retry: Tuple of exceptions that should trigger a retry.
    """
    delay = initial_delay
    for attempt in range(1, max_retries + 2):  # 1 initial run + max_retries
        try:
            return await func()
        except exceptions_to_retry as exc:
            if attempt > max_retries:
                logger.error(
                    "retry_failed_all_attempts",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(exc),
                    exc_info=True,
                )
                raise exc

            # Calculate backoff with jitter
            current_delay = delay + random.uniform(0, jitter)
            logger.warning(
                "retry_attempt_failed",
                attempt=attempt,
                next_retry_in_sec=round(current_delay, 2),
                error=str(exc),
            )

            await asyncio.sleep(current_delay)
            delay *= backoff_factor
